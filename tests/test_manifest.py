"""Source verification must tolerate Git text checkout endings, not alter binaries."""

import hashlib
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "manifest_check", ROOT / "scripts/materialize.py"
)
materialize = importlib.util.module_from_spec(spec)
spec.loader.exec_module(materialize)


class ManifestCheckoutTests(unittest.TestCase):
    def test_git_text_checkout_endings_have_the_same_source_hash(self):
        expected = hashlib.sha256(b"first\nsecond\n").hexdigest()
        for name in (
            "web/app.js",
            "handoff.json",
            "requirements.txt",
            "examples/table.csv",
            ".github/workflows/tests.yml",
            "project.toml",
            ".gitignore",
            "LICENSE",
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    materialize.digest(b"first\r\nsecond\r\n", name), expected
                )

    def test_binary_and_nul_containing_fixtures_keep_exact_bytes(self):
        for name, raw in (
            ("image.png", b"\x89PNG\r\n\x1a\n"),
            ("archive.zip", b"PK\x03\x04\r\n"),
            ("example.txt", b"\x00\r\n"),
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    materialize.digest(raw, name), hashlib.sha256(raw).hexdigest()
                )


if __name__ == "__main__":
    unittest.main()
