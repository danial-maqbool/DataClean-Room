"""Read a PDF in a disposable subprocess. Invoked only by the local app."""

from __future__ import annotations
import json
import sys
from .safety import MAX_TEXT_CHARS


def main() -> None:
    # Unix resource limits are an extra defense. The parent enforces a timeout on all OSes.
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))
    except (ImportError, ValueError, OSError):
        pass
    from pypdf import PdfReader

    reader = PdfReader(sys.argv[1])
    if reader.is_encrypted:
        raise ValueError("Encrypted PDF files are not supported.")
    chunks, length = [], 0
    truncated = len(reader.pages) > 300
    for page in list(reader.pages)[:300]:
        text = page.extract_text() or ""
        chunks.append(text)
        length += len(text)
        if length >= MAX_TEXT_CHARS:
            truncated = True
            break
    text = "\n\n".join(chunks)[:MAX_TEXT_CHARS]
    print(
        json.dumps(
            {
                "text": text,
                "method": "PDF text layer",
                "truncated": truncated,
                "warnings": (
                    ["Scanned image text is not included."] if not text.strip() else []
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
