"""Regression checks for portable output references and browser security."""

from pathlib import PureWindowsPath
from unittest import TestCase
from unittest.mock import patch
from localdesk.base import BaseApplication


class PortabilityTests(TestCase):
    def test_windows_artifact_reference_uses_forward_slashes(self):
        class File(PureWindowsPath):
            def is_file(self):
                return True

            def stat(self):
                class Info:
                    st_size = 4

                return Info()

        app = object.__new__(BaseApplication)
        app.exports = PureWindowsPath("C:/private/exports")
        with patch("localdesk.base.within", return_value=True):
            result = app.artifact(File("C:/private/exports/job-1/result.csv"))
        self.assertEqual(result["path"], "job-1/result.csv")

    def test_browser_checks_do_not_require_unsafe_eval(self):
        from pathlib import Path

        script = Path(__file__).resolve().parents[1] / "scripts/browser_check.py"
        self.assertNotIn("wait_for_function(", script.read_text())
