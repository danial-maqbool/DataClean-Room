"""Verify synthetic redaction output with Poppler, independently of PDFium.

Use a new ignored report directory. The recorded-error cases inject OCR text,
not source pixels. Real-OCR cases run the installed Tesseract executable.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import native
from tests.fixtures import make_pdf
from tests.test_ocr_redaction import scanned_fixture, recorded_layout


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(pdf, target, page=1):
    subprocess.run(
        [
            "pdftoppm",
            "-f",
            str(page),
            "-l",
            str(page),
            "-singlefile",
            "-r",
            "144",
            "-png",
            str(pdf),
            str(target),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    return target.with_suffix(".png")


def assert_regions(image_path, *, sideways=False):
    from PIL import Image

    with Image.open(image_path) as source:
        image = source.convert("RGB")
        if sideways:
            old = image
            image = image.rotate(270, expand=True)
            old.close()
        try:
            # These source-truth regions do not come from the detector or OCR boxes.
            with image.crop((75, 97, 810, 143)) as secret:
                assert (
                    max(v[1] for v in secret.getextrema()) < 32
                ), "Secret glyph region was not masked."
            with image.crop((70, 202, 680, 265)) as public:
                values = public.getextrema()
                assert min(v[0] for v in values) < 80, "Public glyphs were lost."
                assert max(v[1] for v in values) > 220, "Public line was covered."
        finally:
            image.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.report_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "status": "started",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "checks": [],
        "verification": "Poppler renders exported bytes; fixed source-truth pixel regions.",
    }
    target = output / "ocr-redaction-report.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    try:
        for tool in ("pdftoppm", "tesseract"):
            if not shutil.which(tool):
                raise RuntimeError(
                    tool + " is required for this check. No pass was recorded."
                )
        from PIL import Image
        from pypdf import PdfReader, PdfWriter

        source_dir = output / "fixtures"
        source_dir.mkdir()
        scanned = scanned_fixture(source_dir)
        original_hash = sha(scanned)
        source_render = render(scanned, output / "source-scan")
        with Image.open(source_render) as image:
            extrema = image.crop((75, 97, 810, 143)).getextrema()
            assert min(v[0] for v in extrema) < 80 and max(v[1] for v in extrema) > 220
        for recognized in ("OA_SECRET_CANARY", "QXA_SECRET_CANARY", "QA_SECRET_CANRY"):
            with patch("app.native._layout", return_value=recorded_layout(recognized)):
                data, audit = native.clean_pdf(
                    scanned, literals=["QA_SECRET_CANARY"], ocr=True
                )
            file = output / (recognized + ".pdf")
            file.write_bytes(data)
            assert_regions(render(file, file.with_suffix("")))
            assert audit["selected_regions"] == 0 and audit["ocr_review"]["candidates"]
            assert sha(scanned) == original_hash
            report["checks"].append(
                {
                    "case": recognized,
                    "mode": "recorded OCR-error injection",
                    "status": "PASS",
                }
            )
        with Image.open(source_dir / "scan.png") as image:
            sideways = image.rotate(90, expand=True)
            sideways.save(source_dir / "sideways.pdf", "PDF")
            sideways.close()
        native_pdf = make_pdf(
            source_dir / "native.pdf", text="QA_SECRET_CANARY public 42"
        )
        writer = PdfWriter()
        writer.append(str(native_pdf))
        writer.pages[0].rotate(90)
        writer.append(str(source_dir / "sideways.pdf"))
        writer.add_attachment("private.txt", b"PRIVATE_ATTACHMENT")
        writer.add_metadata({"/Author": "PRIVATE_AUTHOR"})
        mixed = source_dir / "mixed.pdf"
        writer.write(mixed)
        for file, page, sideways in ((scanned, 1, False), (mixed, 2, True)):
            before = sha(file)
            result = native.process(
                file.read_bytes(),
                ".pdf",
                "pdf",
                {"ocr": True, "literals": ["QA_SECRET_CANARY"]},
            )
            data = base64.b64decode(result["content"], validate=True)
            clean = output / (file.stem + "-real-ocr.pdf")
            clean.write_bytes(data)
            assert_regions(
                render(clean, clean.with_suffix(""), page), sideways=sideways
            )
            pdf = PdfReader(io.BytesIO(data))
            assert not pdf.attachments and not pdf.get_fields()
            assert "PRIVATE_AUTHOR" not in str(pdf.metadata)
            assert all(
                not (p.extract_text() or "").strip() and not p.get("/Annots")
                for p in pdf.pages
            )
            assert result["audit"]["selected_regions"] == 0
            assert before == sha(file)
            report["checks"].append(
                {
                    "case": file.stem,
                    "mode": "real Tesseract",
                    "status": "PASS",
                    "orientation_attempts": result["audit"]["orientation_attempts"],
                }
            )
        # Unreadable custom text requires explicit review and manual masking.
        doc = recorded_layout("UNREADABLE_MARK")
        with (
            patch("app.native._layout", return_value=doc),
            patch("app.native._recover_orientation", return_value=doc),
        ):
            data, audit = native.clean_pdf(
                scanned,
                literals=["QA_SECRET_CANARY"],
                ocr=True,
                rectangles=[{"page": 1, "rect": [0, 0, 2200, 180]}],
                ocr_review_confirmed=True,
            )
        fallback = output / "manual-fallback.pdf"
        fallback.write_bytes(data)
        assert_regions(render(fallback, fallback.with_suffix("")))
        assert audit["selected_regions"] == 1 and audit["ocr_review_confirmed"]
        report["checks"].append(
            {
                "case": "manual fallback",
                "mode": "recorded OCR-error injection",
                "status": "PASS",
            }
        )
        report["status"] = "passed"
    except Exception:
        report["status"] = "failed"
        report["error"] = traceback.format_exc()
    finally:
        report["source_sha256"] = {
            str(p.relative_to(ROOT)): sha(p)
            for folder in ("app", "tests")
            for p in sorted((ROOT / folder).glob("*.py"))
        }
        report["artifacts_sha256"] = {
            str(p.relative_to(output)): sha(p)
            for p in output.rglob("*")
            if p.is_file() and p != target
        }
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "checks": len(report["checks"]),
                "report": str(target),
            }
        )
    )
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
