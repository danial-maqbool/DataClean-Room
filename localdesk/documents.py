"""Isolated local OCR, document text, and PDF table extraction."""

from __future__ import annotations
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from .safety import InputError, checked_path


def advanced_capabilities() -> dict:
    available = lambda name: importlib.util.find_spec(name) is not None
    return {
        "ocr": bool(shutil.which("tesseract")),
        "pdf_tables": available("pdfplumber"),
        "pdf_render": available("pypdfium2"),
        "encryption": available("cryptography"),
        "semantic_lsa": available("sklearn"),
        "neural_embeddings": available("sentence_transformers"),
        "desktop_package": available("pyautogui"),
        "video_repair": bool(shutil.which("ffmpeg")),
        "keyring": available("keyring"),
    }


def document_request(path: Path, operation: str = "text", **options) -> dict:
    path = checked_path(path)
    if operation not in {"text", "tables", "layout"}:
        raise InputError("Unknown document operation.")
    request = {"path": str(path), "operation": operation, "options": options}
    try:
        result = subprocess.run(
            [sys.executable, "-m", "localdesk.document_worker"],
            input=json.dumps(request),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=90,
            check=False,
            cwd=Path(__file__).resolve().parents[1],
        )
    except subprocess.TimeoutExpired as exc:
        raise InputError(
            "Document processing reached its 90 second limit. Split the input into smaller files."
        ) from exc
    if result.returncode or len(result.stdout) > 12_000_000:
        raise InputError(
            "The document worker stopped. Check the file and installed local tools."
        )
    try:
        data = json.loads(result.stdout)
    except ValueError as exc:
        raise InputError("The document worker returned an invalid result.") from exc
    if "error" in data:
        raise InputError(data["error"])
    return data
