"""Real worker and application checks for OCR review confirmation forwarding."""

import base64
import io
import shutil
from unittest import skipUnless
from PIL import Image
from tests.fixtures import make_image
from tests.support import AppCase


@skipUnless(
    shutil.which("tesseract"), "Tesseract is required for OCR worker integration."
)
class OCRApplicationTests(AppCase):
    def test_image_export_requires_boolean_review_and_keeps_source(self):
        path = make_image(self.workspace / "public.png", text="Public number 42")
        original = path.read_bytes()
        scan = self.finish(
            "scan", {"paths": [str(path)], "ocr": True, "literals": ["MISSINGSECRET"]}
        )
        ident = scan["scans"][0]["id"]
        self.assertTrue(
            self.app.scan(ident)["report"]["ocr_review"]["requires_confirmation"]
        )
        for flag in (False, "true", 1):
            denied = self.finish(
                "sanitize", {"id": ident, "ocr_review_confirmed": flag}, "failed"
            )
            self.assertIn("OCR", denied["error"])
        result = self.finish(
            "sanitize",
            {
                "id": ident,
                "ocr_review_confirmed": True,
                "rectangles": [[0, 0, 100, 90]],
            },
        )
        self.assertTrue(result["audit"]["ocr_review_confirmed"])
        with Image.open(io.BytesIO(self.output(result["output"]))) as image:
            self.assertEqual(image.convert("RGB").getpixel((50, 50)), (0, 0, 0))
        self.assertEqual(path.read_bytes(), original)

    def test_pdf_export_uses_the_same_review_gate(self):
        image = make_image(self.workspace / "public.png", text="Public number 42")
        path = self.workspace / "public.pdf"
        with Image.open(image) as im:
            im.convert("RGB").save(path, "PDF")
        original = path.read_bytes()
        scan = self.finish(
            "scan", {"paths": [str(path)], "ocr": True, "literals": ["MISSINGSECRET"]}
        )
        ident = scan["scans"][0]["id"]
        denied = self.finish("sanitize", {"id": ident}, "failed")
        self.assertIn("confirm the OCR review", denied["error"])
        result = self.finish(
            "sanitize",
            {
                "id": ident,
                "ocr_review_confirmed": True,
                "page_rectangles": [{"page": 1, "rect": [0, 0, 200, 180]}],
            },
        )
        self.assertTrue(result["audit"]["ocr_review_confirmed"])
        from tests.test_ocr_redaction import exported_image

        with exported_image(self.output(result["output"])) as im:
            self.assertLess(max(im.getpixel((50, 50))), 10)
        self.assertEqual(path.read_bytes(), original)
