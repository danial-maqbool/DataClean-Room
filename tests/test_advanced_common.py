"""Local model, parser, service-definition, and HTTP abuse regressions."""

import importlib.util
import io
import json
import os
import plistlib
import shutil
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from unittest.mock import patch
from localdesk.safety import InputError
from localdesk.semantic import SemanticModel, SearchCache, extractive_summary
from localdesk.documents import document_request
from localdesk.services import service_spec, remove
from tests.fixtures import make_pdf, make_image


class AdvancedCommonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def test_model_ranks_relevant_documents(self):
        rows = [
            {"id": 1, "text": "supplier invoice payment accounts total"},
            {"id": 2, "text": "football match player stadium ball"},
            {"id": 3, "text": "supplier bill invoice total payment due"},
        ]
        result = SearchCache().search(rows, "supplier payment")
        self.assertIn(result["results"][0]["id"], {1, 3})
        self.assertIn("semantic", result["engine"])
        self.assertTrue(all(-1 <= r["semantic_score"] <= 1 for r in result["results"]))

    def test_model_cache_invalidated_by_content(self):
        cache = SearchCache()
        rows = [
            {"id": 1, "text": "invoice supplier payment"},
            {"id": 2, "text": "football stadium match"},
        ]
        cache.search(rows, "payment")
        before = cache.fingerprint
        rows[0]["text"] = "university lecture notes"
        cache.search(rows, "lecture")
        self.assertNotEqual(before, cache.fingerprint)

    def test_empty_corpus_and_unknown_query(self):
        self.assertEqual(SearchCache().search([], "invoice")["results"], [])
        self.assertEqual(
            SearchCache().search(
                [{"id": 1, "text": "invoice supplier"}], "zyxwvunknown"
            )["results"],
            [],
        )

    def test_semantic_query_bound(self):
        model = SemanticModel(["invoice payment"])
        with self.assertRaises(InputError):
            model.scores("x" * 4001)

    def test_untrusted_model_modules_are_rejected(self):
        model = self.root / "model"
        model.mkdir()
        (model / "modules.json").write_text('[{"type":"evil.module.Code"}]')
        with self.assertRaises(InputError):
            SemanticModel(["invoice"], str(model))

    def test_summary_contains_only_source_sentences(self):
        text = "Supplier invoices contain the total payment. Football matches happen at the stadium. Supplier payments require invoice records. Receipts contain supplier payment details."
        result = extractive_summary(text, 2)
        self.assertEqual(len(result.splitlines()), 2)
        self.assertTrue(all(line in text for line in result.splitlines()))

    def test_pdf_text_extraction(self):
        path = make_pdf(self.root / "text.pdf")
        result = document_request(path)
        self.assertIn("Invoice total 42", result["text"])

    def test_pdf_table_extraction(self):
        path = make_pdf(self.root / "table.pdf", table=True)
        result = document_request(path, "tables", strategy="lines")
        self.assertEqual(result["table_count"], 1)
        self.assertEqual(result["tables"][0]["rows"][1], ["Invoice A", "42"])

    def test_pdf_bad_strategy_and_columns(self):
        path = make_pdf(self.root / "table.pdf", table=True)
        with self.assertRaises(InputError):
            document_request(path, "tables", strategy="unknown")
        with self.assertRaises(InputError):
            document_request(path, "tables", strategy="ocr", column_edges=[200, 100])

    def test_pdf_rejects_invalid_file(self):
        path = self.root / "bad.pdf"
        path.write_bytes(b"%PDF-1.4 incomplete")
        with self.assertRaises(InputError):
            document_request(path)

    @unittest.skipUnless(
        shutil.which("tesseract"),
        "Tesseract is required for this OCR integration test.",
    )
    def test_actual_tesseract_image_ocr(self):
        path = make_image(self.root / "invoice.png")
        result = document_request(path, ocr=True)
        self.assertIn("7316", result["text"])
        self.assertIn("4200", result["text"])

    @unittest.skipUnless(
        shutil.which("tesseract"),
        "Tesseract is required for this OCR integration test.",
    )
    def test_actual_scanned_pdf_ocr(self):
        from PIL import Image

        path = make_image(self.root / "page.png")
        with Image.open(path) as image:
            image.save(self.root / "scan.pdf", "PDF", resolution=144)
        result = document_request(self.root / "scan.pdf", ocr=True)
        self.assertIn("7316", result["text"])
        self.assertIn("OCR", result["method"])

    def test_invalid_ocr_language_is_rejected(self):
        from localdesk.document_worker import ocr_words

        with self.assertRaises(InputError):
            ocr_words(self.root / "none.png", language="eng; touch injected")

    def test_linux_service_quotes_paths(self):
        spec = service_spec(
            self.root / "Apps 100% $test",
            self.root / "Private Data",
            8111,
            platform="linux",
            home=self.root,
            executable="/usr/bin/python3",
        )
        content = spec["content"].decode()
        self.assertIn("%% $$", content)
        self.assertIn("--keyring", content)
        self.assertNotIn("--allow-desktop", content)
        self.assertIn("--user", spec["install"][0])
        self.assertNotIn("sudo", content)

    def test_macos_service_is_user_launch_agent(self):
        spec = service_spec(
            self.root / "App",
            self.root / "Data",
            8111,
            platform="darwin",
            home=self.root,
            executable="/usr/bin/python3",
        )
        doc = plistlib.loads(spec["content"])
        self.assertTrue(doc["RunAtLoad"])
        self.assertIn("worker", doc["ProgramArguments"])

    def test_windows_service_uses_interactive_user(self):
        spec = service_spec(
            self.root / "App",
            self.root / "Data",
            8111,
            platform="win32",
            home=self.root,
            executable="C:/Python/python.exe",
        )
        tree = ET.fromstring(spec["content"])
        text = " ".join(tree.itertext())
        self.assertIn("InteractiveToken", text)
        self.assertIn("LeastPrivilege", text)
        self.assertIn("--keyring", text)

    def test_service_rejects_control_chars_and_invalid_ports(self):
        with self.assertRaises(InputError):
            service_spec(self.root / "bad\nname", self.root / "data", 8111)
        with self.assertRaises(InputError):
            service_spec(self.root, self.root, 80)

    def test_remove_refuses_unrelated_service_definition(self):
        with patch(
            "localdesk.services.service_spec",
            return_value={"path": self.root / "unknown", "content": b"ours"},
        ):
            with self.assertRaises(InputError):
                remove(self.root, self.root, 8111)

    def test_document_worker_timeout_is_reported(self):
        import subprocess

        path = make_pdf(self.root / "text.pdf")
        with patch(
            "localdesk.documents.subprocess.run",
            side_effect=subprocess.TimeoutExpired("worker", 90),
        ):
            with self.assertRaisesRegex(InputError, "90 second"):
                document_request(path)

    @unittest.skipUnless(
        shutil.which("tesseract"), "Tesseract is required for this mixed-page OCR test."
    )
    def test_mixed_pdf_keeps_native_header_and_scanned_content(self):
        from PIL import Image
        from pypdf import PdfReader, PdfWriter

        image_path = make_image(self.root / "scan-image.png")
        with Image.open(image_path) as image:
            image.save(self.root / "scan-only.pdf", "PDF", resolution=144)
        header = make_pdf(self.root / "header.pdf", text="NATIVE HEADER")
        page = PdfReader(self.root / "scan-only.pdf").pages[0]
        page.merge_page(PdfReader(header).pages[0], expand=True)
        writer = PdfWriter()
        writer.add_page(page)
        mixed = self.root / "mixed.pdf"
        writer.write(mixed)
        result = document_request(mixed, ocr=True)
        self.assertIn("NATIVE", result["text"])
        self.assertIn("7316", result["text"])
