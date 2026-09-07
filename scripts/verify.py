"""Run local tests and write evidence for the actual interpreter and packages."""

from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict", action="store_true", help="Require native tools and zero skips."
    )
    parser.add_argument("--report-dir", type=Path, default=ROOT / "docs",
                        help="Output folder. Use artifacts/local-qa to keep release evidence unchanged.")
    args = parser.parse_args()
    report_dir = args.report_dir.expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "test-report.json").unlink(missing_ok=True)
    os.chdir(ROOT)
    repository = json.loads((ROOT / "project.json").read_text())["repository"]
    if args.strict:
        required = ["tesseract"] + (
            ["ffmpeg", "ffprobe"] if repository == "RecoveryLab" else []
        )
        missing = [name for name in required if not shutil.which(name)]
        if missing:
            parser.error("Missing integration tools: " + ", ".join(missing))
    started = time.monotonic()
    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"), top_level_dir=str(ROOT)
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    packages = {}
    for name in [
        "cryptography",
        "keyring",
        "Pillow",
        "pypdf",
        "pdfplumber",
        "pdfminer.six",
        "pypdfium2",
        "numpy",
        "scikit-learn",
    ]:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    source = {}
    for parent in ["app", "localdesk", "web", "tests", "scripts"]:
        for path in sorted((ROOT / parent).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                source[path.relative_to(ROOT).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    report = {
        "repository": repository,
        "version": json.loads((ROOT / "project.json").read_text(encoding="utf-8"))["version"],
        "python": platform.python_version(),
        "platform": platform.platform(),
        "tests_run": result.testsRun,
        "passed": result.testsRun
        - len(result.failures)
        - len(result.errors)
        - len(result.skipped),
        "failures": [test.id() for test, _ in result.failures],
        "errors": [test.id() for test, _ in result.errors],
        "skipped": [
            {"test": test.id(), "reason": reason} for test, reason in result.skipped
        ],
        "seconds": round(time.monotonic() - started, 3),
        "packages": packages,
        "tools": {
            name: bool(shutil.which(name))
            for name in ["tesseract", "ffmpeg", "ffprobe"]
        },
        "source_sha256": source,
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_commit": os.environ.get("GITHUB_SHA"),
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "test-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return (
        0 if result.wasSuccessful() and (not args.strict or not result.skipped) else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
