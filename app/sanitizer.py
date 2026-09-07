"""Scan text and metadata; export new, explicitly scoped clean copies."""

from __future__ import annotations
import hashlib
import io
import json
import struct
import zipfile
import zlib
from collections import Counter
from pathlib import Path
from localdesk.parsers import (
    IMAGE_EXTENSIONS,
    OFFICE_EXTENSIONS,
    TEXT_EXTENSIONS,
    capabilities,
    extract,
    extract_bytes,
)
from localdesk.safety import (
    InputError,
    MAX_FILE_BYTES,
    archive_name_ok,
    checked_path,
    open_zip,
    safe_xml,
)
from .detectors import KINDS, detect, public_matches, redact

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_KEEP = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"}
MACRO_EXTENSIONS = {".docm": ".docx", ".xlsm": ".xlsx", ".pptm": ".pptx"}


def png_info(raw: bytes) -> dict:
    if not raw.startswith(PNG_SIGNATURE):
        raise InputError("The PNG signature is missing.")
    position, chunks, metadata = 8, [], []
    width = height = 0
    while position + 12 <= len(raw):
        size = struct.unpack(">I", raw[position : position + 4])[0]
        end = position + size + 12
        if size > MAX_FILE_BYTES or end > len(raw):
            raise InputError("The PNG contains a truncated or oversized chunk.")
        kind, payload = (
            raw[position + 4 : position + 8],
            raw[position + 8 : position + 8 + size],
        )
        crc = struct.unpack(">I", raw[position + 8 + size : end])[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != crc:
            raise InputError(
                "A PNG chunk failed its CRC check. Repair the image before cleaning it."
            )
        if kind == b"IHDR":
            if size != 13 or chunks:
                raise InputError("The PNG header is invalid.")
            width, height = struct.unpack(">II", payload[:8])
            if not 0 < width * height <= 40_000_000:
                raise InputError("The image exceeds the 40 megapixel limit.")
        elif not chunks:
            raise InputError("The first PNG chunk is not an image header.")
        if kind not in PNG_KEEP:
            metadata.append(
                {
                    "label": kind.decode("ascii", errors="replace") + " image chunk",
                    "category": "metadata",
                    "bytes": size,
                }
            )
            if not (kind[0] & 32) and kind not in PNG_KEEP:
                raise InputError("An unsupported critical PNG chunk is present.")
        chunks.append((kind, position, end))
        position = end
        if kind == b"IEND":
            break
    if (
        not chunks
        or chunks[-1][0] != b"IEND"
        or not any(c[0] == b"IDAT" for c in chunks)
    ):
        raise InputError("The PNG image data or end chunk is missing.")
    if position < len(raw):
        metadata.append(
            {
                "label": "Data after PNG end marker",
                "category": "metadata",
                "bytes": len(raw) - position,
            }
        )
    return {
        "width": width,
        "height": height,
        "metadata": metadata,
        "chunks": chunks,
        "animated": any(c[0] == b"acTL" for c in chunks),
    }


def strip_png(raw: bytes) -> tuple[bytes, list[str]]:
    info = png_info(raw)
    cleaned = PNG_SIGNATURE + b"".join(
        raw[start:end] for kind, start, end in info["chunks"] if kind in PNG_KEEP
    )
    notes = [
        "Removed nonessential chunks and trailing data. Pixel data was not changed.",
        "Embedded color profiles were removed. Some viewers may display colors differently.",
    ]
    if info["animated"]:
        notes.append(
            "Animation metadata was removed. The output keeps the default static image only."
        )
    return cleaned, notes


def office_metadata(raw: bytes) -> list[dict]:
    findings = []
    with open_zip(raw) as archive:
        names = archive.namelist()
        for name in names:
            if name.startswith("docProps/"):
                findings.append(
                    {"category": "metadata", "label": "Document properties: " + name}
                )
            elif "comments" in name.casefold():
                findings.append(
                    {"category": "comments", "label": "Comment part: " + name}
                )
            elif "/embeddings/" in name or name.lower().endswith("vbaproject.bin"):
                findings.append(
                    {"category": "embedded", "label": "Embedded object or macro part"}
                )
            elif name.startswith("customXml/"):
                findings.append({"category": "custom_xml", "label": "Custom XML part"})
            if name.endswith(".rels"):
                tree = safe_xml(archive.read(name))
                count = sum(
                    n.attrib.get("TargetMode") == "External" for n in tree.iter()
                )
                if count:
                    findings.append(
                        {
                            "category": "external_links",
                            "label": f"{count} external relationship(s) in {name}",
                        }
                    )
        if "xl/workbook.xml" in names:
            tree = safe_xml(archive.read("xl/workbook.xml"))
            hidden = sum(
                n.attrib.get("state") in {"hidden", "veryHidden"} for n in tree.iter()
            )
            if hidden:
                findings.append(
                    {
                        "category": "hidden_content",
                        "label": f"{hidden} hidden worksheet(s)",
                    }
                )
        if "word/document.xml" in names:
            tree = safe_xml(archive.read("word/document.xml"))
            revisions = sum(
                n.tag.rsplit("}", 1)[-1] in {"ins", "del"} for n in tree.iter()
            )
            if revisions:
                findings.append(
                    {
                        "category": "revision",
                        "label": f"{revisions} tracked change element(s)",
                    }
                )
    return findings


def jpeg_metadata(raw: bytes) -> list[dict]:
    if not raw.startswith(b"\xff\xd8"):
        raise InputError("The JPEG signature is missing.")
    offset, fields = 2, []
    while offset + 4 <= len(raw):
        if raw[offset] != 0xFF:
            break
        while offset < len(raw) and raw[offset] == 0xFF:
            offset += 1
        if offset >= len(raw):
            break
        marker = raw[offset]
        offset += 1
        if marker in {0xDA, 0xD9}:
            break
        length = struct.unpack(">H", raw[offset : offset + 2])[0]
        if length < 2 or offset + length > len(raw):
            raise InputError("A JPEG header segment is truncated.")
        if 0xE1 <= marker <= 0xEF or marker == 0xFE:
            labels = {
                0xE1: "EXIF or XMP metadata",
                0xE2: "ICC profile or application metadata",
                0xED: "IPTC or Photoshop metadata",
                0xFE: "JPEG comment",
            }
            fields.append(
                {
                    "category": "metadata",
                    "label": labels.get(marker, "JPEG application metadata"),
                    "bytes": length,
                }
            )
        offset += length
    return fields


def image_clean(
    raw: bytes, extension: str, rectangles: list | None = None
) -> tuple[bytes, list[str]]:
    rectangles = rectangles or []
    if extension == ".png" and not rectangles and not capabilities()["images"]:
        return strip_png(raw)
    if not capabilities()["images"]:
        raise InputError(
            "Pixel redaction and JPEG cleaning need Pillow. Install requirements-optional.txt."
        )
    from PIL import Image, ImageDraw, ImageOps

    if len(rectangles) > 100:
        raise InputError("Use at most 100 image redaction rectangles.")
    with Image.open(io.BytesIO(raw)) as original:
        if original.width * original.height > 40_000_000:
            raise InputError("The image exceeds the 40 megapixel limit.")
        oriented = ImageOps.exif_transpose(original)
        oriented.load()
        mode = "RGBA" if "A" in oriented.getbands() else "RGB"
        converted = oriented.convert(mode)
        # A new pixel-only object prevents inherited EXIF, text, or format metadata.
        fresh = Image.new(mode, converted.size)
        fresh.paste(converted)
        drawer = ImageDraw.Draw(fresh)
        for rectangle in rectangles:
            if not isinstance(rectangle, (list, tuple)) or len(rectangle) != 4:
                raise InputError(
                    "Each redaction rectangle needs four pixel coordinates."
                )
            try:
                x1, y1, x2, y2 = [int(v) for v in rectangle]
            except (ValueError, TypeError) as exc:
                raise InputError("Rectangle coordinates must be integers.") from exc
            if not (0 <= x1 < x2 <= fresh.width and 0 <= y1 < y2 <= fresh.height):
                raise InputError("A redaction rectangle is outside the image.")
            drawer.rectangle(
                (x1, y1, x2 - 1, y2 - 1),
                fill=(0, 0, 0, 255) if mode == "RGBA" else (0, 0, 0),
            )
        output = io.BytesIO()
        fresh.save(output, format="PNG", optimize=True)
    return output.getvalue(), [
        f"Redrew {len(rectangles)} selected pixel region(s).",
        "Exported the first image frame as a new PNG without source metadata.",
        "Check the visible image. Metadata removal does not remove unselected text or faces.",
    ]


def analyze(
    path: Path, *, enabled=None, literals=None, ocr=False, include_text=False
) -> dict:
    path = checked_path(path)
    raw, ext = path.read_bytes(), path.suffix.lower()
    report = {
        "name": path.name,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "format": ext,
        "matches": [],
        "counts": {},
        "metadata": [],
        "warnings": [],
        "coverage": [],
        "text_length": 0,
        "truncated": False,
        "supported": False,
        "export_mode": "none",
        "status": "review_required",
    }
    text = ""
    if ext == ".zip":
        return analyze_archive(raw, path.name, enabled=enabled, literals=literals)
    if ext in OFFICE_EXTENSIONS or ext in MACRO_EXTENSIONS:
        report["metadata"] = office_metadata(raw)
        parsed = extract_bytes(raw, MACRO_EXTENSIONS.get(ext, ext))
        text = parsed["text"]
        report.update(
            {"truncated": parsed["truncated"], "supported": True, "export_mode": "text"}
        )
        report["warnings"].extend(parsed["warnings"])
        report["coverage"] = [
            "Extracted Office text",
            "Known property, comment, link, and revision parts",
        ]
        report["warnings"].append(
            "Export creates plain text. It does not modify or preserve the original Office document layout."
        )
    elif ext in TEXT_EXTENSIONS or ext == ".pdf":
        parsed = extract(path, ocr=False)
        text = parsed["text"]
        report.update(
            {"truncated": parsed["truncated"], "supported": True, "export_mode": "text"}
        )
        report["warnings"].extend(parsed["warnings"])
        report["coverage"] = [
            "Available text layer" if ext == ".pdf" else "Decoded text"
        ]
        if ext == ".pdf":
            report["warnings"].append(
                "PDF images, attachments, form values, and hidden objects are not fully scanned. Export is plain text, not a redacted PDF."
            )
    elif ext in IMAGE_EXTENSIONS:
        report["export_mode"] = "image"
        if ext == ".png":
            info = png_info(raw)
            report.update(
                {
                    "metadata": info["metadata"],
                    "width": info["width"],
                    "height": info["height"],
                    "supported": True,
                }
            )
            report["coverage"].append("PNG chunk structure and nonessential metadata")
        elif ext in {".jpg", ".jpeg"}:
            report["metadata"] = jpeg_metadata(raw)
            report["supported"] = capabilities()["images"]
            report["coverage"].append("JPEG header metadata segments")
        else:
            report["supported"] = capabilities()["images"]
            report["coverage"].append("Optional Pillow image reader")
        if capabilities()["images"]:
            from PIL import Image, ImageOps

            with Image.open(io.BytesIO(raw)) as im:
                oriented = ImageOps.exif_transpose(im)
                report["width"], report["height"] = oriented.size
                if oriented.width * oriented.height > 40_000_000:
                    raise InputError("The image exceeds the 40 megapixel limit.")
        if ocr:
            parsed = extract(path, ocr=True)
            text = parsed["text"]
            report["warnings"].extend(parsed["warnings"])
            report["coverage"].append("Local OCR text, subject to recognition errors")
        else:
            report["warnings"].append(
                "Image pixels were not scanned for private text or faces. Check visible content yourself."
            )
        report["warnings"].append(
            "Metadata cleaning alone does not remove information visible in image pixels."
        )
    else:
        report["warnings"].append(
            "This file type is unsupported. No clean-copy claim can be made."
        )
    matches = detect(text, enabled=enabled, literals=literals)
    report["matches"] = public_matches(matches)
    report["counts"] = dict(Counter(m["kind"] for m in matches))
    report["text_length"] = len(text)
    report["findings"] = len(matches) + len(report["metadata"])
    report["warnings"].append(
        "Pattern checks can miss private information or mark harmless text. Review the result before sharing it."
    )
    if include_text:
        report["text"] = text
        report["preview"] = redact(text, matches)
    return report


def clean_text(
    path: Path, *, enabled=None, literals=None, mode="labels", accept_partial=False
) -> tuple[bytes, dict]:
    report = _legacy_analyze(
        path, enabled=enabled, literals=literals, include_text=True
    )
    if report["export_mode"] != "text" or not report["supported"]:
        raise InputError("This input does not support a plain-text clean copy.")
    if report["truncated"] and not accept_partial:
        raise InputError(
            "Only part of this document was scanned. Explicitly allow a partial text export, or split the input."
        )
    matches = detect(report["text"], enabled=enabled, literals=literals)
    cleaned = redact(report["text"], matches, mode)
    audit = {
        "removed_matches": len(matches),
        "categories": report["counts"],
        "source_sha256": report["sha256"],
        "output_format": "UTF-8 plain text",
        "partial": report["truncated"],
        "coverage": report["coverage"],
        "warnings": report["warnings"],
        "source_metadata_copied": False,
        "note": "The exported text is a new file. The original document is unchanged.",
    }
    return cleaned.encode("utf-8"), audit


def analyze_archive(raw: bytes, name: str, *, enabled=None, literals=None) -> dict:
    members, total = [], 0
    with open_zip(raw) as archive:
        if len(archive.infolist()) > 100:
            raise InputError(
                "Privacy scanning supports at most 100 archive entries per batch."
            )
        for info in archive.infolist():
            if info.is_dir():
                continue
            ext = Path(info.filename).suffix.lower()
            item = {
                "name": info.filename,
                "supported": False,
                "matches": 0,
                "metadata": 0,
                "note": "",
            }
            if (
                not archive_name_ok(info.filename)
                or info.flag_bits & 1
                or ((info.external_attr >> 16) & 0o170000) == 0o120000
            ):
                item["note"] = (
                    "Unsafe, linked, or encrypted archive entry. Excluded from clean export."
                )
            else:
                try:
                    data = archive.read(info)
                    if ext in TEXT_EXTENSIONS or ext in OFFICE_EXTENSIONS:
                        parsed = extract_bytes(data, ext)
                        if parsed["truncated"]:
                            raise InputError(
                                "Text is truncated. This entry will not be exported."
                            )
                        matches = detect(
                            parsed["text"], enabled=enabled, literals=literals
                        )
                        item.update(
                            {
                                "supported": True,
                                "matches": len(matches),
                                "export": "plain text",
                            }
                        )
                        if ext in OFFICE_EXTENSIONS:
                            item["metadata"] = len(office_metadata(data))
                    elif ext == ".png":
                        image = png_info(data)
                        item.update(
                            {
                                "supported": True,
                                "metadata": len(image["metadata"]),
                                "export": "metadata-stripped PNG",
                                "note": "Visible pixels are not scanned or redacted.",
                            }
                        )
                    else:
                        item["note"] = (
                            "Unsupported or nested archive entry. Excluded from clean export."
                        )
                except Exception as exc:
                    item["note"] = str(exc)[:250]
            total += item["matches"] + item["metadata"]
            members.append(item)
    return {
        "name": name,
        "size": len(raw),
        "format": ".zip",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "members": members,
        "matches": [],
        "counts": {},
        "metadata": [],
        "findings": total,
        "coverage": ["Supported top-level archive members"],
        "truncated": False,
        "text_length": 0,
        "supported": any(m["supported"] for m in members),
        "export_mode": "archive",
        "status": "review_required",
        "warnings": [
            "Clean export excludes unsupported entries and replaces file names with generic names.",
            "PNG image pixels remain visible. Review them before sharing the archive.",
            "Nested archives and PDF entries are not processed inside ZIP files.",
        ],
    }


def clean_archive(
    raw: bytes, *, enabled=None, literals=None, mode="labels"
) -> tuple[bytes, dict]:
    report = analyze_archive(raw, "input.zip", enabled=enabled, literals=literals)
    output = io.BytesIO()
    exported, excluded = 0, 0
    with (
        open_zip(raw) as source,
        zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target,
    ):
        for index, info in enumerate(i for i in source.infolist() if not i.is_dir()):
            member = report["members"][index]
            if not member["supported"]:
                excluded += 1
                continue
            content, extension = source.read(info), Path(info.filename).suffix.lower()
            exported += 1
            if extension == ".png":
                clean, _ = strip_png(content)
                filename = f"image-{exported:03d}.png"
            else:
                text = extract_bytes(content, extension)["text"]
                clean = redact(
                    text, detect(text, enabled=enabled, literals=literals), mode
                ).encode("utf-8")
                filename = f"document-{exported:03d}.txt"
            target.writestr(filename, clean)
        manifest = {
            "exported_files": exported,
            "excluded_files": excluded,
            "original_filenames_copied": False,
            "source_archive_modified": False,
            "warnings": report["warnings"],
        }
        target.writestr("clean-copy-report.json", json.dumps(manifest, indent=2))
    if not exported:
        raise InputError("No supported archive entries can be exported.")
    if len(output.getvalue()) > MAX_FILE_BYTES:
        raise InputError("The clean archive exceeds the 25 MiB output limit.")
    return output.getvalue(), manifest


_legacy_analyze = analyze


def analyze(
    path: Path, *, enabled=None, literals=None, ocr=False, include_text=False
) -> dict:
    """Extend text scanning with real page layout and fresh Office exports."""
    from .native import OFFICE, request

    path = checked_path(path)
    suffix = path.suffix.lower()
    if suffix not in OFFICE | {".pdf"} and not (ocr and suffix in IMAGE_EXTENSIONS):
        return _legacy_analyze(
            path,
            enabled=enabled,
            literals=literals,
            ocr=False,
            include_text=include_text,
        )
    if suffix in OFFICE:
        report = _legacy_analyze(
            path,
            enabled=enabled,
            literals=literals,
            ocr=False,
            include_text=include_text,
        )
        report["export_mode"] = "office"
        report["warnings"] = [w for w in report["warnings"] if "plain text" not in w]
        report["warnings"].append(
            "Native export rebuilds visible text and cells. Graphics, hidden content, comments, macros, and original formatting are not copied. Review the new document."
        )
        return report
    raw = path.read_bytes()
    result = request(raw, suffix, "layout", enabled=enabled, literals=literals, ocr=ocr)
    if suffix == ".pdf":
        report = {
            "name": path.name,
            "format": suffix,
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "metadata": [],
            "truncated": False,
            "supported": True,
            "export_mode": "pdf",
            "status": "review_required",
            "coverage": [
                "Native PDF text and page positions",
                "Reconstructed raster-page export",
            ],
            "warnings": [],
        }
    else:
        report = _legacy_analyze(
            path, enabled=enabled, literals=literals, ocr=False, include_text=False
        )
    report.update(
        matches=result["matches"],
        counts=result["counts"],
        pages=result["pages"],
        automatic_regions=result.get("automatic_regions", []),
        ocr_review=result.get("ocr_review", {}),
        text_length=len(result["text"]),
        findings=len(result["matches"]) + len(report["metadata"]),
    )
    report["coverage"].append(result["method"])
    report["warnings"].extend(result["warnings"])
    report["warnings"].append(
        "Review all page pixels. Detection can miss private text, faces, and unlabelled information."
    )
    if suffix == ".pdf" and not ocr:
        report["warnings"].append(
            "OCR was disabled. Image-only text needs manual regions or a new scan with OCR enabled."
        )
    if include_text:
        report["text"] = result["text"]
        report["preview"] = redact(
            result["text"], detect(result["text"], enabled=enabled, literals=literals)
        )
    return report
