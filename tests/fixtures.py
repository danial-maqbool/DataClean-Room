"""Small synthetic files for offline regression tests. No personal data or font files."""

from pathlib import Path


def make_pdf(path: Path, *, text="Invoice total 42", table=False):
    if table:
        stream = b"0.5 w 30 260 m 300 260 l S 30 220 m 300 220 l S 30 180 m 300 180 l S 30 140 m 300 140 l S 30 140 m 30 260 l S 170 140 m 170 260 l S 300 140 m 300 260 l S\n"
        cells = [
            (40, 235, "Item"),
            (180, 235, "Total"),
            (40, 195, "Invoice A"),
            (180, 195, "42"),
            (40, 155, "Invoice B"),
            (180, 155, "75"),
        ]
        for x, y, value in cells:
            stream += f"BT /F1 14 Tf {x} {y} Td ({value}) Tj ET\n".encode()
    else:
        value = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 18 Tf 30 230 Td ({value}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 300] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
    ]
    raw = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(raw))
        raw.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(raw)
    raw.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        raw.extend(f"{offset:010d} 00000 n \n".encode())
    raw.extend(
        f"trailer\n<< /Root 1 0 R /Size {len(objects)+1} >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(raw)
    return path


def make_image(path: Path, text="INVOICE REF 7316\nTotal amount 4200"):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1100, 220), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=38)
    draw.multiline_text((30, 35), text, font=font, fill="black", spacing=20)
    image.save(path)
    image.close()
    return path
