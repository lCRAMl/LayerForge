"""Small synthetic PDFs for recognition tests (reportlab, test-only dependency).

Layouts are given top-down like on paper: (x, y_from_top, w, h) in points on A4.
"""

from __future__ import annotations

from pathlib import Path

A4_W, A4_H = 595.0, 842.0


def grid(x, y, cols, rows, w, h, gap):
    return [(x + c * (w + gap), y + r * (h + gap), w, h) for r in range(rows) for c in range(cols)]


def vector_pdf(path: Path, rects, filled: bool = True, text: str = "Pattern A") -> Path:
    from reportlab.lib.colors import Color
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=(A4_W, A4_H))
    c.setFont("Helvetica", 11)
    c.drawString(40, A4_H - 30, text)
    for x, y, w, h in rects:
        if filled:
            c.setFillColor(Color(0.70, 0.36, 0.24))
            c.setStrokeColor(Color(0.70, 0.36, 0.24))
            c.rect(x, A4_H - y - h, w, h, stroke=0, fill=1)
        else:
            c.setStrokeColor(Color(0, 0, 0))
            c.setLineWidth(1.5)
            c.rect(x, A4_H - y - h, w, h, stroke=1, fill=0)
    c.showPage()
    c.save()
    return path


def raster_pdf(path: Path, rects, skew: float = 0.0, dpi: float = 150.0) -> Path:
    """A page that is one embedded image, optionally rotated by `skew` degrees."""
    import cv2
    import numpy as np
    from reportlab.pdfgen import canvas

    scale = dpi / 72.0
    img = np.full((int(A4_H * scale), int(A4_W * scale), 3), 255, np.uint8)
    for x, y, w, h in rects:
        cv2.rectangle(img, (int(x * scale), int(y * scale)),
                      (int((x + w) * scale) - 1, int((y + h) * scale) - 1), (60, 92, 180), -1)
    if skew:
        hh, ww = img.shape[:2]
        matrix = cv2.getRotationMatrix2D((ww / 2, hh / 2), skew, 1.0)
        img = cv2.warpAffine(img, matrix, (ww, hh), borderValue=(255, 255, 255))
    png = path.with_suffix(".png")
    cv2.imwrite(str(png), img)
    c = canvas.Canvas(str(path), pagesize=(A4_W, A4_H))
    c.drawImage(str(png), 0, 0, A4_W, A4_H)
    c.showPage()
    c.save()
    return path
