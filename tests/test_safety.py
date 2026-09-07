"""Input limits, copy semantics, bounded parsers, storage, and local jobs."""

import base64
import json
import os
import sqlite3
import threading
import time
import unittest
from pathlib import Path
from localdesk.safety import (
    InputError,
    MAX_FILE_BYTES,
    archive_name_ok,
    checked_path,
    clean_name,
    digest,
    integer,
    open_zip,
    safe_xml,
    unique_write,
    walk_files,
    within,
)
from localdesk.parsers import decode_text, extract_bytes
from tests.support import AppCase, zipped


class SafetyTests(AppCase):
    def test_empty_path_is_rejected(self):
        with self.assertRaises(InputError):
            checked_path("")

    def test_directory_and_file_types_are_checked(self):
        p = self.file()
        with self.assertRaises(InputError):
            checked_path(p, directory=True)
        with self.assertRaises(InputError):
            checked_path(self.workspace)

    def test_output_does_not_overwrite(self):
        p = self.file(content="original")
        with self.assertRaises(FileExistsError):
            unique_write(p, b"replacement")
        self.assertEqual(p.read_text(), "original")

    def test_new_output_has_exact_bytes(self):
        p = self.workspace / "new.txt"
        unique_write(p, b"new\x00bytes")
        self.assertEqual(p.read_bytes(), b"new\x00bytes")

    def test_windows_reserved_name_is_escaped(self):
        self.assertEqual(clean_name("CON.txt"), "_CON.txt")

    def test_upload_filename_cannot_escape_inbox(self):
        r = self.app.common_post(
            "upload",
            {"name": "../../secret.txt", "content": base64.b64encode(b"data").decode()},
        )
        self.assertTrue(within(Path(r["path"]), self.app.data / "inbox"))
        self.assertEqual(Path(r["path"]).name, "secret.txt")

    def test_invalid_base64_is_rejected(self):
        with self.assertRaises(InputError):
            self.app.common_post("upload", {"content": "!!not_base64!!"})

    def test_source_cannot_be_downloaded_as_output(self):
        self.file()
        with self.assertRaises(InputError):
            self.app.download("../../workspace/sample.txt")

    def test_download_rejects_absolute_external_path(self):
        with self.assertRaises(InputError):
            self.app.download(str(self.file()))

    def test_integer_rejects_fraction_bool_and_range(self):
        for value in [True, 1.2, "1.2", -1, 100]:
            with self.subTest(value=value), self.assertRaises(InputError):
                integer(value, 0, 10)
        self.assertEqual(integer("4", 0, 10), 4)

    def test_archive_path_rules(self):
        for path in [
            "../bad",
            "/absolute",
            "C:bad",
            "a\\b",
            "a/../../b",
            "bad\x00name",
        ]:
            with self.subTest(path=path):
                self.assertFalse(archive_name_ok(path))
        self.assertTrue(archive_name_ok("folder/report.txt"))

    def test_xml_external_entities_are_rejected(self):
        for raw in [
            b"<!DOCTYPE a><a/>",
            b'<!ENTITY x SYSTEM "file:///etc/passwd"><a/>',
        ]:
            with self.assertRaises(InputError):
                safe_xml(raw)

    def test_utf16_xml_entities_are_rejected(self):
        with self.assertRaises(InputError):
            safe_xml("<!DOCTYPE a><a/>".encode("utf-16"))

    def test_high_expansion_archive_is_rejected(self):
        with self.assertRaises(InputError):
            open_zip(zipped({"large.txt": b"a" * 1_100_000}))

    def test_symlink_input_is_rejected(self):
        source = self.file()
        link = self.workspace / "link.txt"
        try:
            link.symlink_to(source)
        except (OSError, NotImplementedError):
            self.skipTest("This OS account cannot create symbolic links.")
        with self.assertRaises(InputError):
            checked_path(link)

    def test_default_scan_excludes_private_and_build_folders(self):
        self.file(".git/config")
        self.file("node_modules/a.txt")
        self.file(".env")
        p = self.file("keep.txt")
        self.assertEqual(list(walk_files(self.workspace)), [p])

    def test_scan_file_limit_is_explicit(self):
        self.file("a.txt")
        self.file("b.txt")
        with self.assertRaises(InputError):
            list(walk_files(self.workspace, limit=1))

    def test_text_encodings(self):
        for raw, wanted in [
            (b"plain", "plain"),
            ("Hello".encode("utf-16"), "Hello"),
            (b"caf\xe9", "café"),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(decode_text(raw)[0], wanted)

    def test_text_extraction_rejects_binary(self):
        with self.assertRaises(InputError):
            extract_bytes(b"a\x00b", ".txt")

    def test_text_limit_is_reported(self):
        parsed = extract_bytes(b"a" * 250_001, ".txt")
        self.assertTrue(parsed["truncated"])
        self.assertEqual(len(parsed["text"]), 250_000)

    def test_docx_text_and_paragraphs(self):
        raw = zipped(
            {"word/document.xml": "<document><p>Hello</p><p>World</p></document>"}
        )
        self.assertEqual(extract_bytes(raw, ".docx")["text"], "Hello\nWorld")

    def test_pptx_slide_order_is_numeric(self):
        raw = zipped(
            {
                "ppt/slides/slide10.xml": "<s><p>Ten</p></s>",
                "ppt/slides/slide2.xml": "<s><p>Two</p></s>",
            }
        )
        self.assertEqual(extract_bytes(raw, ".pptx")["text"], "Two\nTen")

    def test_xlsx_shared_and_inline_values(self):
        raw = zipped(
            {
                "xl/sharedStrings.xml": "<sst><si><t>Shared text</t></si></sst>",
                "xl/worksheets/sheet1.xml": '<worksheet><row><c t="s"><v>0</v></c><c><v>42</v></c></row></worksheet>',
            }
        )
        self.assertEqual(extract_bytes(raw, ".xlsx")["text"], "Shared text\t42")

    def test_opendocument_text(self):
        self.assertEqual(
            extract_bytes(
                zipped({"content.xml": "<document><p>Local notes</p></document>"}),
                ".odt",
            )["text"],
            "Local notes",
        )

    def test_database_backup_requires_persistent_encryption(self):
        self.app.store.set("test", "value")
        with self.assertRaises(InputError):
            self.app.common_post("backup", {})

    def test_job_success_and_error_are_persisted(self):
        good = self.app.jobs.submit("Test success", lambda c: {"ok": True})
        self.assertEqual(self.wait(good), {"ok": True})

        def fail(c):
            raise ValueError("expected failure")

        bad = self.app.jobs.submit("Test failure", fail)
        self.assertIn("expected failure", self.wait(bad, "failed")["error"])

    def test_job_cancellation_is_cooperative(self):
        started = threading.Event()

        def long_job(c):
            started.set()
            for _ in range(1000):
                c.check()
                time.sleep(0.003)

        ident = self.app.jobs.submit("Test cancellation", long_job)
        self.assertTrue(started.wait(2))
        self.app.jobs.cancel(ident)
        self.wait(ident, "cancelled")

    def test_unknown_job_is_rejected(self):
        with self.assertRaises(InputError):
            self.app.jobs.get("not-a-job")

    def test_output_larger_than_input_limit_can_be_downloaded(self):
        p = self.app.new_output("large") / "backup.bin"
        with p.open("wb") as stream:
            stream.truncate(MAX_FILE_BYTES + 1)
        self.assertEqual(self.app.download(self.app.artifact(p)["path"]), p)
