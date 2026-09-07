"""Pixel-level regressions for recorded OCR failures and real local OCR."""

import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
from unittest import TestCase
from unittest.mock import patch

from app import native
from app.ocr_matching import document_matches
from localdesk.safety import InputError
from tests.fixtures import make_image, make_pdf


def scanned_fixture(folder):
    from PIL import Image

    image = make_image(folder / "scan.png", text="QA_SECRET_CANARY\nPublic number 42")
    pdf = folder / "scanned.pdf"
    with Image.open(image) as source:
        source.convert("RGB").save(pdf, "PDF")
    return pdf


def recorded_layout(value="OA_SECRET_CANARY"):
    # Only recognized text is injected. The real source pixels retain the Q.
    text = value + "\nPublic number 42\n"
    return {
        "text": text,
        "truncated": False,
        "warnings": [],
        "method": "Recorded OCR error injection",
        "pages": [
            {
                "page": 1,
                "width": 1100,
                "height": 220,
                "words": [
                    {
                        "text": value,
                        "start": 0,
                        "end": len(value),
                        "bbox": [30, 35, 470, 85],
                        "line": 0,
                        "confidence": 54.0,
                    },
                    {
                        "text": "Public number 42",
                        "start": len(value) + 1,
                        "end": len(text) - 1,
                        "bbox": [30, 95, 340, 140],
                        "line": 1,
                        "confidence": 96.0,
                    },
                ],
            }
        ],
    }


def exported_image(data, page=0):
    # Decode the actual PDF image with pypdf and Pillow, not the export renderer.
    from pypdf import PdfReader

    pdf = PdfReader(io.BytesIO(data), strict=True)
    return pdf.pages[page].images[0].image.convert("RGB")


class OCRRedactionTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.pdf = scanned_fixture(self.folder)

    def assert_canary_masked_and_public_visible(self, data):
        from PIL import ImageStat

        with exported_image(data) as image:
            # Fixed source-truth region, independent of detected word boxes.
            with image.crop((80, 90, 850, 145)) as secret:
                self.assertLess(
                    max(x[1] for x in secret.getextrema()),
                    32,
                    "Secret band still contains unmasked pixels",
                )
            with image.crop((70, 202, 680, 265)) as public:
                extrema = public.getextrema()
                self.assertLess(min(x[0] for x in extrema), 80, "Public text was lost")
                self.assertGreater(
                    max(x[1] for x in extrema), 220, "Public line was over-masked"
                )

    def test_recorded_substitution_masks_exported_pixels(self):
        before = hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        with patch("app.native._layout", return_value=recorded_layout()):
            data, audit = native.clean_pdf(
                self.pdf, literals=["QA_SECRET_CANARY"], ocr=True
            )
        self.assert_canary_masked_and_public_visible(data)
        self.assertEqual(len(audit["ocr_review"]["candidates"]), 1)
        self.assertEqual(audit["selected_regions"], 0)
        self.assertEqual(before, hashlib.sha256(self.pdf.read_bytes()).hexdigest())

    def test_recorded_insertions_and_deletions_mask_pixels(self):
        for text in ["QXA_SECRET_CANARY", "QA_SECRET_CANRY"]:
            with (
                self.subTest(text=text),
                patch("app.native._layout", return_value=recorded_layout(text)),
            ):
                data, _ = native.clean_pdf(
                    self.pdf, literals=["QA_SECRET_CANARY"], ocr=True
                )
                self.assert_canary_masked_and_public_visible(data)

    def test_layout_and_export_use_the_same_candidate_spans(self):
        raw = self.pdf.read_bytes()
        with patch("app.native._layout", side_effect=lambda *a: recorded_layout()):
            scan = native.process(
                raw, ".pdf", "layout", {"literals": ["QA_SECRET_CANARY"], "ocr": True}
            )
            result = native.process(
                raw, ".pdf", "pdf", {"literals": ["QA_SECRET_CANARY"], "ocr": True}
            )
        self.assertEqual(scan["counts"], {"custom": 1})
        self.assertEqual(len(scan["automatic_regions"]), 1)
        self.assertEqual(scan["ocr_review"], result["audit"]["ocr_review"])
        self.assert_canary_masked_and_public_visible(
            base64.b64decode(result["content"])
        )
        self.assertNotIn("QA_SECRET_CANARY", json.dumps(result["audit"]))
        self.assertNotIn("OA_SECRET_CANARY", json.dumps(result["audit"]))

    def test_unlocated_literal_blocks_unconfirmed_export(self):
        doc = recorded_layout("UNREADABLE_MARK")
        with (
            patch("app.native._layout", return_value=doc),
            patch("app.native._recover_orientation", return_value=doc),
        ):
            with self.assertRaisesRegex(InputError, "confirm the OCR review"):
                native.clean_pdf(self.pdf, literals=["QA_SECRET_CANARY"], ocr=True)
        self.assertTrue(self.pdf.exists())

    def test_manual_fallback_after_unlocated_literal(self):
        doc = recorded_layout("UNREADABLE_MARK")
        with (
            patch("app.native._layout", return_value=doc),
            patch("app.native._recover_orientation", return_value=doc),
        ):
            data, audit = native.clean_pdf(
                self.pdf,
                literals=["QA_SECRET_CANARY"],
                ocr=True,
                rectangles=[{"page": 1, "rect": [0, 0, 2200, 180]}],
                ocr_review_confirmed=True,
            )
        self.assert_canary_masked_and_public_visible(data)
        self.assertEqual(audit["removed_matches"], 0)
        self.assertEqual(audit["selected_regions"], 1)
        self.assertTrue(audit["ocr_review_confirmed"])
        self.assertTrue(audit["ocr_review"]["unmatched_rule_ids"])

    def test_confirmation_does_not_bypass_invalid_manual_geometry(self):
        doc = recorded_layout("UNREADABLE_MARK")
        with (
            patch("app.native._layout", return_value=doc),
            patch("app.native._recover_orientation", return_value=doc),
        ):
            with self.assertRaisesRegex(InputError, "outside"):
                native.clean_pdf(
                    self.pdf,
                    literals=["QA_SECRET_CANARY"],
                    ocr=True,
                    rectangles=[{"page": 1, "rect": [0, 0, 9999, 90]}],
                    ocr_review_confirmed=True,
                )

    def test_text_only_pdf_exact_detector_is_unchanged(self):
        p = make_pdf(self.folder / "native.pdf", text="PRIVATEVALUE public 42")
        data, audit = native.clean_pdf(p, literals=["PRIVATEVALUE"])
        self.assertGreater(audit["painted_regions"], 0)
        self.assertFalse(audit["ocr_review"]["candidates"])
        from pypdf import PdfReader

        self.assertEqual(PdfReader(io.BytesIO(data)).pages[0].extract_text(), "")

    def test_all_quarter_turn_coordinate_transforms(self):
        # Draw in the rotated coordinate system and verify the inverse box on the original.
        from PIL import Image, ImageDraw

        width, height = 120, 80
        for angle in (90, 180, 270):
            source = Image.new("L", (width, height), 255)
            ImageDraw.Draw(source).rectangle((15, 20, 44, 39), fill=0)
            rotated = source.rotate(angle, expand=True)
            from PIL import ImageOps

            box = ImageOps.invert(rotated).getbbox()
            self.assertEqual(
                native._undo_rotation(box, angle, width, height), [15, 20, 45, 40]
            )
            source.close()
            rotated.close()

    def test_same_source_metadata_is_not_copied(self):
        from pypdf import PdfReader, PdfWriter

        writer = PdfWriter()
        writer.append(str(self.pdf))
        writer.add_attachment("secret.txt", b"PRIVATE_ATTACHMENT")
        writer.add_metadata({"/Author": "PRIVATE_AUTHOR"})
        stream = io.BytesIO()
        writer.write(stream)
        with patch("app.native._layout", return_value=recorded_layout()):
            result = native.process(
                stream.getvalue(),
                ".pdf",
                "pdf",
                {"ocr": True, "literals": ["QA_SECRET_CANARY"]},
            )
        data = base64.b64decode(result["content"])
        self.assert_canary_masked_and_public_visible(data)
        pdf = PdfReader(io.BytesIO(data))
        self.assertFalse(pdf.attachments)
        self.assertFalse(pdf.get_fields())
        self.assertNotIn("PRIVATE_AUTHOR", str(pdf.metadata))
        self.assertNotIn(b"PRIVATE_ATTACHMENT", data)
        self.assertFalse(pdf.pages[0].get("/Annots"))

    def test_real_ocr_upright_scanned_pdf(self):
        if not shutil.which("tesseract"):
            self.skipTest("Tesseract is required for the real OCR test.")
        result = native.process(
            self.pdf.read_bytes(),
            ".pdf",
            "pdf",
            {"ocr": True, "literals": ["QA_SECRET_CANARY"]},
        )
        data = base64.b64decode(result["content"])
        with exported_image(data) as image:
            # Source-truth glyph interior. Real OCR boxes are tighter than the injected boxes.
            self.assertLess(
                max(x[1] for x in image.crop((75, 97, 810, 143)).getextrema()), 32
            )
            self.assertGreater(
                max(x[1] for x in image.crop((70, 202, 680, 265)).getextrema()), 220
            )
        self.assertGreater(result["audit"]["painted_regions"], 0)
        self.assertEqual(result["audit"]["selected_regions"], 0)

    def test_real_ocr_rotated_scan_and_mixed_document(self):
        if not shutil.which("tesseract"):
            self.skipTest("Tesseract is required for the real OCR test.")
        from PIL import Image
        from pypdf import PdfWriter, PdfReader

        with Image.open(self.folder / "scan.png") as im:
            rotated = im.rotate(90, expand=True)
            rotated.save(self.folder / "sideways.pdf", "PDF")
            rotated.close()
        p = make_pdf(self.folder / "native.pdf", text="QA_SECRET_CANARY public 42")
        writer = PdfWriter()
        writer.append(str(p))
        writer.append(str(self.folder / "sideways.pdf"))
        writer.pages[0].rotate(90)
        out = io.BytesIO()
        writer.write(out)
        result = native.process(
            out.getvalue(),
            ".pdf",
            "pdf",
            {"ocr": True, "literals": ["QA_SECRET_CANARY"]},
        )
        data = base64.b64decode(result["content"])
        self.assertEqual(len(PdfReader(io.BytesIO(data)).pages), 2)
        self.assertGreater(result["audit"]["orientation_attempts"], 0)
        with exported_image(data, 1) as sideways:
            im = sideways.rotate(270, expand=True)
            try:
                self.assertLess(
                    max(x[1] for x in im.crop((75, 97, 810, 143)).getextrema()), 32
                )
                self.assertGreater(
                    max(x[1] for x in im.crop((70, 202, 680, 265)).getextrema()), 220
                )
            finally:
                im.close()
