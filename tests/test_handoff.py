"""Regression tests for clean setup and separate local test evidence."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="handoff test ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.preflight = load("preflight_under_test", ROOT / "scripts/preflight.py")

    def test_requirement_markers(self):
        (self.root / "requirements.txt").write_text('numpy==2.3.5\npython-xlib==0.33; sys_platform == "linux"\n')
        result = self.preflight.requirements(self.root, "requirements.txt", "win32")
        self.assertEqual(result, {"numpy": "2.3.5"})
        self.assertIn("python-xlib", self.preflight.requirements(self.root, "requirements.txt", "linux"))

    def test_nested_requirements_and_cycles(self):
        (self.root / "requirements.txt").write_text('numpy==2.3.5\n-r requirements-dev.txt\n')
        (self.root / "requirements-dev.txt").write_text('-r requirements.txt\nplaywright==1.57.0\n')
        result = self.preflight.requirements(self.root, "requirements-dev.txt", "linux")
        self.assertEqual(len(result), 2)

    def test_requirement_path_escape_rejected(self):
        with self.assertRaises(ValueError):
            self.preflight.requirements(self.root, "../requirements.txt", "linux")

    def test_unpinned_requirement_rejected(self):
        (self.root / "requirements.txt").write_text('numpy>=2\n')
        with self.assertRaises(ValueError):
            self.preflight.requirements(self.root, "requirements.txt", "linux")

    def test_package_version_mismatch_is_not_passed(self):
        with patch.object(self.preflight.importlib.metadata, "version", return_value="1.0"):
            result = self.preflight.package_status({"example": "2.0"})
        self.assertFalse(result["example"]["matches"])

    def test_sqlite_check_leaves_no_database_file(self):
        self.assertTrue(self.preflight.sqlite_status()["fts5"])
        self.assertFalse(list(self.root.glob("*.db")))

    def test_dev_installer_is_project_local_and_can_be_offline(self):
        installer = load("bootstrap_under_test", ROOT / "bootstrap.py")
        (self.root / "wheelhouse").mkdir()
        python = self.root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        python.parent.mkdir(parents=True)
        python.touch()
        with patch.object(installer, "__file__", str(self.root / "bootstrap.py")), \
             patch.object(installer.sys, "argv", ["bootstrap.py", "--dev", "--offline", "--wheelhouse", str(self.root / "wheelhouse")]), \
             patch.object(installer.subprocess, "run") as run:
            self.assertEqual(installer.main(), 0)
        command = run.call_args_list[0].args[0]
        self.assertEqual(command[0], str(python))
        self.assertIn("--require-virtualenv", command)
        self.assertIn("--no-index", command)
        self.assertIn(str(self.root / "requirements-dev.txt"), command)

    def test_custom_test_report_keeps_release_report_unchanged(self):
        scripts = self.root / "scripts"
        scripts.mkdir()
        shutil.copyfile(ROOT / "scripts/verify.py", scripts / "verify.py")
        for name in ["tests", "app", "localdesk", "web", "docs"]:
            (self.root / name).mkdir()
        (self.root / "project.json").write_text(json.dumps({"repository": "Synthetic", "version": "9.8.7"}))
        (self.root / "tests/__init__.py").touch()
        (self.root / "tests/test_one.py").write_text('import unittest\nclass Example(unittest.TestCase):\n    def test_ok(self): self.assertTrue(True)\n')
        baseline = self.root / "docs/test-report.json"
        baseline.write_text("release evidence must stay unchanged")
        result = subprocess.run([sys.executable, str(scripts / "verify.py"), "--report-dir", "artifacts/local-qa"],
                                cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(baseline.read_text(), "release evidence must stay unchanged")
        report = json.loads((self.root / "artifacts/local-qa/test-report.json").read_text())
        self.assertEqual(report["passed"], 1)
        self.assertEqual(report["version"], "9.8.7")
        self.assertIn("scripts/verify.py", report["source_sha256"])

    def test_browser_cli_supports_separate_reports(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/browser_check.py"), "--help"],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--report-dir", result.stdout)

    def test_office_runtime_dependencies_are_declared_when_used(self):
        repository = json.loads((ROOT / "project.json").read_text())["repository"]
        if repository == "DataClean-Room":
            req = self.preflight.requirements(ROOT, "requirements.txt", sys.platform)
            self.assertEqual(req["python-docx"], "1.2.0")
            self.assertEqual(req["openpyxl"], "3.1.5")
            self.assertEqual(req["python-pptx"], "1.0.2")
        else:
            self.assertIn("cryptography", self.preflight.requirements(ROOT, "requirements.txt", sys.platform))


if __name__ == "__main__":
    unittest.main()
