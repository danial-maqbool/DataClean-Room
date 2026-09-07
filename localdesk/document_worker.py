"""Bounded parser subprocess. It never follows links embedded in a document."""

from __future__ import annotations
import csv
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from .safety import InputError, MAX_TEXT_CHARS, checked_path, integer

MAX_PAGES = 50
MAX_PIXELS = 20_000_000
MAX_WORDS = 50_000


def ocr_words(image_path: Path, language="eng") -> list[dict]:
    if not isinstance(language, str) or not re.fullmatch(
        r"[A-Za-z0-9_+]{1,64}", language
    ):
        raise InputError("Choose a local Tesseract language, such as eng or eng+urd.")
    binary = shutil.which("tesseract")
    if not binary:
        raise InputError("Install Tesseract and its language data to use OCR.")
    try:
        result = subprocess.run(
            [binary, str(image_path), "stdout", "-l", language, "--psm", "6", "tsv"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise InputError("OCR reached its 30 second page limit.") from exc
    if result.returncode:
        raise InputError(
            "Tesseract could not read this page. Check the installed language data."
        )
    words = []
    for row in csv.DictReader(
        io.StringIO(result.stdout), delimiter="\t", quoting=csv.QUOTE_NONE
    ):
        text = (row.get("text") or "").strip()
        if row.get("level") != "5" or not text:
            continue
        try:
            x, y, w, h = (float(row[k]) for k in ("left", "top", "width", "height"))
            confidence = float(row["conf"])
        except (ValueError, KeyError, TypeError):
            continue
        words.append(
            {
                "text": text,
                "bbox": [x, y, x + w, y + h],
                "confidence": confidence,
                "line": [row.get(k, "0") for k in ("block_num", "par_num", "line_num")],
            }
        )
        if len(words) > MAX_WORDS:
            raise InputError("The page contains too many OCR words.")
    return words


def render_page(path: Path, number: int, scale=2):
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        page = pdf[number]
        try:
            width, height = page.get_size()
            if (
                not all(math.isfinite(v) and v > 0 for v in (width, height))
                or width * height * scale * scale > MAX_PIXELS
            ):
                raise InputError("This PDF page exceeds the raster size limit.")
            bitmap = page.render(scale=scale)
            try:
                image = bitmap.to_pil().convert("RGB").copy()
            finally:
                bitmap.close()
            return image, width, height
        finally:
            page.close()
    finally:
        pdf.close()


def layout(path: Path, *, ocr=False, language="eng", max_pages=MAX_PAGES) -> dict:
    max_pages = integer(max_pages, 1, MAX_PAGES, "Page limit")
    pages, warnings = [], []
    if path.suffix.lower() == ".pdf":
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            if len(pdf.pages) > max_pages:
                raise InputError(
                    f"This PDF has more than {max_pages} pages. Split the document first."
                )
            for index, page in enumerate(pdf.pages):
                native = page.extract_words()[: MAX_WORDS + 1]
                if len(native) > MAX_WORDS:
                    raise InputError("This page has too many text objects.")
                words = [
                    {
                        "text": w["text"],
                        "bbox": [w["x0"], w["top"], w["x1"], w["bottom"]],
                        "line": round(w["top"] / 3),
                    }
                    for w in native
                ]
                method = "PDF text"
                if ocr:
                    image, width, height = render_page(path, index)
                    with tempfile.TemporaryDirectory(prefix="localdesk-ocr-") as temp:
                        rendered = Path(temp) / "page.png"
                        image.save(rendered)
                        recognized = ocr_words(rendered, language)
                    for word in recognized:
                        word["bbox"] = [v / 2 for v in word["bbox"]]
                        x0, y0, x1, y1 = word["bbox"]
                        center_x, center_y = (x0 + x1) / 2, (y0 + y1) / 2
                        # Keep reliable native words. Add OCR words from image
                        # regions even when this page also has native text.
                        if not any(
                            w["bbox"][0] <= center_x <= w["bbox"][2]
                            and w["bbox"][1] - 2 <= center_y <= w["bbox"][3] + 2
                            for w in words[: len(native)]
                        ):
                            words.append(word)
                    if len(words) > MAX_WORDS:
                        raise InputError(
                            "This page has too many combined native and OCR words."
                        )
                    words.sort(key=lambda w: (round(w["bbox"][1] / 4), w["bbox"][0]))
                    for word in words:
                        word["line"] = round(word["bbox"][1] / 4)
                    method = "PDF text + Tesseract OCR" if native else "Tesseract OCR"
                    warnings.append(f"Page {index+1}: OCR text needs review.")
                elif not native:
                    warnings.append(
                        f"Page {index+1}: no selectable text. Enable OCR for this scan."
                    )
                pages.append(
                    {
                        "page": index + 1,
                        "width": float(page.width),
                        "height": float(page.height),
                        "words": words,
                        "method": method,
                    }
                )
                page.close()
    else:
        from PIL import Image, ImageOps

        with Image.open(path) as original:
            if original.width * original.height > MAX_PIXELS:
                raise InputError("This image exceeds 20 million pixels.")
            if getattr(original, "n_frames", 1) != 1:
                raise InputError("Use one image frame per file for OCR.")
            image = ImageOps.exif_transpose(original).convert("RGB")
            width, height = image.size
            with tempfile.TemporaryDirectory(prefix="localdesk-ocr-") as temp:
                rendered = Path(temp) / "image.png"
                image.save(rendered)
                words = ocr_words(rendered, language)
            pages.append(
                {
                    "page": 1,
                    "width": width,
                    "height": height,
                    "words": words,
                    "method": "Tesseract OCR",
                }
            )
            warnings.append("OCR text needs review against the source image.")
    parts, position = [], 0
    for page in pages:
        previous = None
        for word in page["words"]:
            line = word.get("line")
            separator = "\n" if previous != line else " "
            if position:
                parts.append(separator)
                position += len(separator)
            value = word["text"]
            word["start"], word["end"] = position, position + len(value)
            position += len(value)
            parts.append(value)
            previous = line
            if position > MAX_TEXT_CHARS:
                raise InputError(
                    "This document exceeds 250,000 extracted characters. Split the input."
                )
        parts.append("\n")
        position += 1
    text = "".join(parts)
    return {
        "text": text,
        "pages": pages,
        "warnings": list(dict.fromkeys(warnings)),
        "truncated": False,
        "method": " + ".join(sorted({p["method"] for p in pages})),
    }


def tables(
    path: Path, *, strategy="lines", language="eng", column_edges=None, **unused
) -> dict:
    if path.suffix.lower() != ".pdf":
        raise InputError("PDF table extraction needs a .pdf input.")
    if strategy not in {"lines", "text", "ocr"}:
        raise InputError("Choose lines, text, or ocr as the table strategy.")
    output = []
    if strategy in {"lines", "text"}:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            if len(pdf.pages) > MAX_PAGES:
                raise InputError(
                    "Split PDFs with more than 50 pages before extracting tables."
                )
            for page in pdf.pages:
                settings = {
                    "vertical_strategy": strategy,
                    "horizontal_strategy": strategy,
                }
                for index, found in enumerate(page.find_tables(settings)):
                    rows = found.extract()
                    if len(rows) > 2000 or any(len(row) > 100 for row in rows):
                        raise InputError("The table exceeds 2,000 rows or 100 columns.")
                    output.append(
                        {
                            "page": page.page_number,
                            "table": index + 1,
                            "bbox": list(found.bbox),
                            "rows": [[str(v or "") for v in row] for row in rows],
                            "method": f"PDF {strategy} table extraction",
                        }
                    )
                page.close()
    else:
        data = layout(path, ocr=True, language=language)
        for page in data["pages"]:
            edges = column_edges or []
            if not isinstance(edges, list) or len(edges) > 99:
                raise InputError("Use an ordered list of up to 99 column boundaries.")
            if edges and (
                any(
                    isinstance(x, bool)
                    or not isinstance(x, (int, float))
                    or not math.isfinite(x)
                    or not 0 < x < page["width"]
                    for x in edges
                )
                or edges != sorted(set(edges))
            ):
                raise InputError(
                    "Column boundaries must be increasing page x coordinates."
                )
            groups = {}
            for word in page["words"]:
                key = str(word["line"])
                groups.setdefault(key, []).append(word)
            rows = []
            for group in groups.values():
                group.sort(key=lambda w: w["bbox"][0])
                if edges:
                    row = [""] * (len(edges) + 1)
                    for w in group:
                        col = sum(w["bbox"][0] >= x for x in edges)
                        row[col] = (row[col] + " " + w["text"]).strip()
                else:
                    row = []
                    right = None
                    for w in group:
                        if right is None or w["bbox"][0] - right > max(
                            14, page["width"] / 30
                        ):
                            row.append(w["text"])
                        else:
                            row[-1] += " " + w["text"]
                        right = w["bbox"][2]
                rows.append(row)
            if rows:
                output.append(
                    {
                        "page": page["page"],
                        "table": 1,
                        "bbox": [0, 0, page["width"], page["height"]],
                        "rows": rows,
                        "method": "OCR/word-position table candidates",
                    }
                )
    cells = sum(len(row) for t in output for row in t["rows"])
    if cells > 20000:
        raise InputError("The combined tables exceed 20,000 cells.")
    return {
        "tables": output,
        "warnings": [
            "Check cell boundaries, merged cells, and OCR values before using this export."
        ],
        "strategy": strategy,
        "table_count": len(output),
    }


def main():
    try:
        request = json.loads(sys.stdin.read(200000))
        path = checked_path(request.get("path", ""))
        op = request.get("operation", "text")
        options = request.get("options", {})
        if not isinstance(options, dict):
            raise InputError("Options must be an object.")
        if op == "tables":
            result = tables(path, **options)
        else:
            result = layout(path, **options)
            if op == "text":
                result.pop("pages", None)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        message = (
            str(exc)[:350]
            if isinstance(exc, (InputError, ImportError))
            else f"The parser rejected this document ({type(exc).__name__})."
        )
        print(json.dumps({"error": message}))


if __name__ == "__main__":
    # CPU limits contain loops in native parsers on Unix. Page, pixel and text
    # limits apply on every supported OS. This is not an OS security sandbox.
    if os.name != "nt":
        try:
            import resource

            resource.setrlimit(resource.RLIMIT_CPU, (85, 90))
        except (ImportError, ValueError, OSError):
            pass
    main()
