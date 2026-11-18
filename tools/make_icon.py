"""Render layerforge/resources/icons/layerforge.svg into a multi-size Windows .ico.

Run after changing the SVG:  python tools/make_icon.py
Each size is rendered from the vector source (crisp at 16 px) and stored as PNG
inside the ICO container, which Windows Vista and later read directly.
"""

import struct
import sys
from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

ICONS = Path(__file__).resolve().parents[1] / "layerforge" / "resources" / "icons"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def png(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def main() -> int:
    QGuiApplication(sys.argv[:1])
    renderer = QSvgRenderer(str(ICONS / "layerforge.svg"))
    images = [(size, png(renderer, size)) for size in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, blobs = b"", b""
    for size, blob in images:
        edge = 0 if size >= 256 else size          # 0 means 256 in the ICO directory
        entries += struct.pack("<BBBBHHII", edge, edge, 0, 0, 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)
    (ICONS / "layerforge.ico").write_bytes(header + entries + blobs)
    (ICONS / "layerforge_256.png").write_bytes(images[-1][1])
    print(f"wrote {ICONS / 'layerforge.ico'} ({len(images)} sizes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
