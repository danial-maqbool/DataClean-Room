"""Pattern checks, conservative copy exports, metadata stripping, and audit limits."""

import io
import json
import unittest
import zipfile
from app.detectors import detect, redact, luhn, valid_iban
from app.sanitizer import (
    analyze,
    clean_archive,
    clean_text,
    image_clean,
    png_info,
    strip_png,
)
from localdesk.parsers import capabilities
from localdesk.safety import InputError, digest
from tests.support import AppCase, ROOT, zipped


class PrivacyTests(AppCase):
    def test_email_pattern(self):
        self.assertEqual(detect("Email alex@example.test")[0]["kind"], "email")

    def test_luhn_known_test_number(self):
        self.assertTrue(luhn("4111 1111 1111 1111"))
        self.assertFalse(luhn("4111 1111 1111 1112"))
        self.assertFalse(luhn("0000 0000 0000 0000"))

    def test_valid_iban_checksum(self):
        self.assertTrue(valid_iban("GB82 WEST 1234 5698 7654 32"))
        self.assertFalse(valid_iban("GB83 WEST 1234 5698 7654 32"))

    def test_invalid_ip_is_not_ipv4(self):
        self.assertFalse(any(m["kind"] == "ipv4" for m in detect("999.2.3.4")))

    def test_labeled_name_keeps_label(self):
        text = "Name: Alex Example"
        r = redact(text, detect(text))
        self.assertEqual(r, "Name: [NAME_1]")

    def test_unlabeled_name_is_not_claimed_detected(self):
        self.assertEqual(detect("Alex Example"), [])

    def test_custom_text_is_literal_not_regex(self):
        text = "Project [A] and Project B"
        m = detect(text, literals=["Project [A]"])
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["value"], "Project [A]")

    def test_overlapping_detectors_do_not_duplicate_ranges(self):
        m = detect("Card: 4111 1111 1111 1111")
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["kind"], "card")

    def test_repeated_values_have_stable_labels(self):
        text = "a@example.test then a@example.test"
        r = redact(text, detect(text))
        self.assertEqual(r, "[EMAIL_1] then [EMAIL_1]")

    def test_blocks_mode(self):
        text = "a@example.test"
        self.assertEqual(redact(text, detect(text), "blocks"), "[REDACTED]")

    def test_unknown_detector_is_rejected(self):
        with self.assertRaises(InputError):
            detect("", enabled=["face_recognition"])

    def test_empty_enabled_list_disables_patterns(self):
        self.assertEqual(detect("a@example.test", enabled=[]), [])

    def test_public_report_omits_detected_values(self):
        p = self.file(content="a@example.test")
        r = analyze(p)
        self.assertNotIn("a@example.test", json.dumps(r))
        self.assertEqual(r["findings"], 1)

    def test_text_copy_really_removes_matched_value(self):
        p = self.file(content="Email: a@example.test\nPublic note")
        h = digest(p)
        raw, audit = clean_text(p)
        self.assertNotIn(b"a@example.test", raw)
        self.assertIn(b"Public note", raw)
        self.assertEqual(digest(p), h)

    def test_partial_text_requires_explicit_acceptance(self):
        p = self.file(content="a" * 250_001)
        with self.assertRaises(InputError):
            clean_text(p)
        raw, audit = clean_text(p, accept_partial=True)
        self.assertTrue(audit["partial"])
        self.assertEqual(len(raw), 250_000)

    def test_office_output_is_plain_text_not_fake_docx(self):
        p = self.file(
            "private.docx",
            zipped(
                {
                    "word/document.xml": "<d><p>Name: Alex Example</p></d>",
                    "docProps/core.xml": "<properties><creator>Private author</creator></properties>",
                }
            ),
        )
        raw, audit = clean_text(p)
        self.assertEqual(raw, b"Name: [NAME_1]")
        self.assertFalse(raw.startswith(b"PK"))

    def test_png_metadata_is_removed_without_changing_idat(self):
        raw = (ROOT / "examples/image-with-comment.png").read_bytes()
        clean, notes = strip_png(raw)
        before = png_info(raw)
        after = png_info(clean)
        self.assertTrue(before["metadata"])
        self.assertEqual(after["metadata"], [])
        self.assertEqual(
            (before["width"], before["height"]), (after["width"], after["height"])
        )
        self.assertNotIn(b"Synthetic private metadata", clean)

    def test_archive_omits_unknown_entries_and_private_names(self):
        raw = zipped(
            {
                "private-name-contact.txt": "Email a@example.test",
                "unknown.bin": b"\x00\x01",
                "nested.zip": zipped({"x.txt": "secret"}),
            }
        )
        clean, audit = clean_archive(raw)
        with zipfile.ZipFile(io.BytesIO(clean)) as archive:
            self.assertNotIn("private-name-contact.txt", archive.namelist())
            self.assertEqual(
                set(archive.namelist()), {"document-001.txt", "clean-copy-report.json"}
            )
            self.assertNotIn(b"a@example.test", archive.read("document-001.txt"))
        self.assertEqual(audit["excluded_files"], 2)

    def test_archive_traversal_is_excluded(self):
        clean, audit = clean_archive(
            zipped({"../escape.txt": "secret", "good.txt": "public"})
        )
        with zipfile.ZipFile(io.BytesIO(clean)) as archive:
            self.assertEqual(
                set(archive.namelist()), {"document-001.txt", "clean-copy-report.json"}
            )

    def test_full_scan_and_export_preserves_source(self):
        p = self.file(content="Email a@example.test")
        h = digest(p)
        scan = self.finish("scan", {"paths": [str(p)]})
        r = self.finish("sanitize", {"id": scan["scans"][0]["id"]})
        self.assertTrue(r["audit"]["original_unchanged"])
        self.assertEqual(digest(p), h)
        self.assertNotIn(b"a@example.test", self.output(r["output"]))
        self.assertNotIn("a@example.test", json.dumps(r["audit"]))

    def test_changed_source_is_rejected(self):
        p = self.file(content="a@example.test")
        r = self.finish("scan", {"paths": [str(p)]})
        p.write_text("changed")
        error = self.finish("sanitize", {"id": r["scans"][0]["id"]}, expected="failed")
        self.assertIn("source changed", error["error"])

    def test_unsupported_binary_cannot_be_clean_exported(self):
        p = self.file("secret.bin", b"\x00\x01")
        r = self.finish("scan", {"paths": [str(p)]})
        with self.assertRaises(InputError):
            self.app.post("sanitize", {"id": r["scans"][0]["id"]})

    @unittest.skipUnless(capabilities()["images"], "Optional Pillow is not installed.")
    def test_pixel_rectangles_are_opaque_and_metadata_free(self):
        from PIL import Image

        raw = (ROOT / "examples/image-with-comment.png").read_bytes()
        clean, _ = image_clean(raw, ".png", [[0, 0, 20, 20]])
        with Image.open(io.BytesIO(clean)) as im:
            self.assertEqual(im.getpixel((5, 5))[:3], (0, 0, 0))
            self.assertEqual(im.info, {})

    @unittest.skipUnless(capabilities()["images"], "Optional Pillow is not installed.")
    def test_image_rectangle_bounds_are_validated(self):
        raw = (ROOT / "examples/image-with-comment.png").read_bytes()
        with self.assertRaises(InputError):
            image_clean(raw, ".png", [[-1, 0, 20, 20]])

    @unittest.skipUnless(capabilities()["images"], "Optional Pillow is not installed.")
    def test_exif_orientation_matches_clean_pixel_dimensions(self):
        from PIL import Image

        image = Image.new("RGB", (30, 10))
        exif = Image.Exif()
        exif[274] = 6
        stream = io.BytesIO()
        image.save(stream, format="PNG", exif=exif)
        clean, _ = image_clean(stream.getvalue(), ".png")
        with Image.open(io.BytesIO(clean)) as out:
            self.assertEqual(out.size, (10, 30))
            self.assertFalse(out.getexif())
