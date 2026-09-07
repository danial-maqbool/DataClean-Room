"""Bounded text extraction. No macros, links, or document code are executed."""

from __future__ import annotations
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from .safety import (
    InputError,
    MAX_FILE_BYTES,
    MAX_TEXT_CHARS,
    checked_path,
    open_zip,
    safe_xml,
)

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".html",
    ".css",
    ".xml",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".rst",
    ".sql",
    ".sh",
    ".bat",
    ".c",
    ".cpp",
    ".h",
    ".java",
    ".rs",
    ".go",
    ".srt",
    ".vtt",
}
OFFICE_EXTENSIONS = {".docx", ".pptx", ".xlsx", ".odt", ".ods", ".odp"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}


def capabilities() -> dict:
    return {
        "pdf": importlib.util.find_spec("pypdf") is not None,
        "images": importlib.util.find_spec("PIL") is not None,
        "ocr": shutil.which("tesseract") is not None,
        "git": shutil.which("git") is not None,
    }


def decode_text(raw: bytes) -> tuple[str, str]:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "UTF-16"
    try:
        return raw.decode("utf-8-sig"), "UTF-8"
    except UnicodeDecodeError:
        if b"\x00" in raw:
            raise InputError("This input appears to be binary, not text.")
        try:
            return raw.decode("cp1252"), "Windows-1252"
        except UnicodeDecodeError as exc:
            raise InputError("The text encoding is not supported.") from exc


def office_text(raw: bytes, extension: str) -> str:
    with open_zip(raw) as archive:
        names = archive.namelist()
        if extension == ".docx":
            selected = sorted(
                n
                for n in names
                if n == "word/document.xml"
                or re.fullmatch(r"word/(header|footer)\d+\.xml", n)
            )
        elif extension == ".pptx":
            selected = sorted(
                (n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                key=lambda n: int(re.search(r"(\d+)\.xml", n).group(1)),
            )
        elif extension == ".xlsx":
            shared = []
            if "xl/sharedStrings.xml" in names:
                tree = safe_xml(archive.read("xl/sharedStrings.xml"))
                shared = ["".join(n.itertext()) for n in tree]
            chunks = []
            length = 0
            for name in sorted(
                n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)
            ):
                tree = safe_xml(archive.read(name))
                for row in tree.iter():
                    if row.tag.rsplit("}", 1)[-1] != "row":
                        continue
                    cells = []
                    for cell in row:
                        values = [
                            n.text or ""
                            for n in cell.iter()
                            if n.tag.rsplit("}", 1)[-1] in {"v", "t"}
                        ]
                        value = "".join(values)
                        if cell.attrib.get("t") == "s" and value.isdigit():
                            idx = int(value)
                            value = (
                                shared[idx]
                                if idx < len(shared)
                                else "[invalid shared string]"
                            )
                        cells.append(value)
                    value = "\t".join(cells)
                    chunks.append(value)
                    length += len(value) + 1
                    if length > MAX_TEXT_CHARS:
                        return "\n".join(chunks)[:MAX_TEXT_CHARS]
            return "\n".join(chunks)
        else:
            selected = ["content.xml"] if "content.xml" in names else []
        if not selected:
            raise InputError("The document has no supported text part.")
        chunks = []
        length = 0
        for name in selected:
            tree = safe_xml(archive.read(name))
            # Preserve paragraph boundaries instead of joining every word with spaces.
            paras = [n for n in tree.iter() if n.tag.rsplit("}", 1)[-1] in {"p", "h"}]
            for p in paras or [tree]:
                value = "".join(p.itertext())
                chunks.append(value)
                length += len(value)
                if length >= MAX_TEXT_CHARS:
                    return "\n".join(chunks)[:MAX_TEXT_CHARS]
        return "\n".join(chunks)


def extract_bytes(raw: bytes, extension: str) -> dict:
    if len(raw) > MAX_FILE_BYTES:
        raise InputError("The input exceeds 25 MiB.")
    extension = extension.lower()
    if extension in TEXT_EXTENSIONS:
        text, encoding = decode_text(raw)
        if "\x00" in text:
            raise InputError("The file contains binary data.")
        return {
            "text": text[:MAX_TEXT_CHARS],
            "method": encoding,
            "truncated": len(text) > MAX_TEXT_CHARS,
            "warnings": [],
        }
    if extension in OFFICE_EXTENSIONS:
        text = office_text(raw, extension)
        return {
            "text": text,
            "method": "Office XML",
            "truncated": len(text) >= MAX_TEXT_CHARS,
            "warnings": [
                "Images, charts, and embedded objects are not converted to text."
            ],
        }
    raise InputError(
        f'Text extraction is not available for {extension or "this file type"}.'
    )


def extract(path: Path, *, ocr: bool = False) -> dict:
    path = checked_path(path)
    ext = path.suffix.lower()
    if ext == ".pdf" or (ext in IMAGE_EXTENSIONS and ocr):
        from .documents import document_request

        return document_request(path, "text", ocr=ocr)
    if ext in IMAGE_EXTENSIONS:
        return {
            "text": "",
            "method": "Filename and metadata only",
            "truncated": False,
            "warnings": ["Image text was not scanned. OCR is disabled."],
        }
    return extract_bytes(path.read_bytes(), ext)
