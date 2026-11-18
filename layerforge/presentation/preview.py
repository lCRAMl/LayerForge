"""Small pattern pictures for the pattern list, its hover pop-up and proposals.

Rendered from the domain model with QPainter, never captured from the PDF. The cache
key is the geometry itself (immutable packages + example values), so a picture is
rebuilt only when geometry, orientation or package count actually change.
"""

from __future__ import annotations

from collections import OrderedDict

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen

from layerforge.domain.geometry import rects
from layerforge.domain.model import Pattern
from layerforge.presentation.theme import editor_colors

_CACHE: OrderedDict[tuple, QImage] = OrderedDict()
_CACHE_MAX = 400


def pattern_image(pattern: Pattern, size: int, ratio: float = 1.0,
                  marked: tuple[int, ...] = (), marked_color: QColor | None = None) -> QImage:
    colors = editor_colors()
    key = (pattern.packages, pattern.dims, size, round(ratio * 100), marked,
           colors.package_fill.rgba(), None if marked_color is None else marked_color.rgba())
    image = _CACHE.get(key)
    if image is not None:
        _CACHE.move_to_end(key)
        return image
    image = render(pattern, size, ratio, marked, marked_color)
    _CACHE[key] = image
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return image


def render(pattern: Pattern, size: int, ratio: float = 1.0, marked=(), marked_color=None) -> QImage:
    colors = editor_colors()
    px = max(1, round(size * ratio))
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(ratio)
    image.fill(Qt.GlobalColor.transparent)
    if not pattern.packages or not pattern.dims.is_valid():
        return image
    try:
        boxes = rects(pattern.packages, pattern.dims)
    except ValueError:
        return image
    x0 = min(b.x0 for b in boxes)
    y0 = min(b.y0 for b in boxes)
    x1 = max(b.x1 for b in boxes)
    y1 = max(b.y1 for b in boxes)
    margin = 3.0
    scale = (size - 2 * margin) / max(x1 - x0, y1 - y0, 1)
    off_x = margin + (size - 2 * margin - (x1 - x0) * scale) / 2
    off_y = margin + (size - 2 * margin - (y1 - y0) * scale) / 2

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    edge = QPen(colors.package_edge, 1.0)
    for index, b in enumerate(boxes):
        # Y up in the pattern, Y down in the image.
        r = QRectF(off_x + (b.x0 - x0) * scale, off_y + (y1 - b.y1) * scale,
                   (b.x1 - b.x0) * scale, (b.y1 - b.y0) * scale).adjusted(0.5, 0.5, -0.5, -0.5)
        fill = marked_color if index in marked and marked_color is not None else colors.preview_fill
        painter.setPen(edge)
        painter.setBrush(fill)
        painter.drawRect(r)
    painter.end()
    return image

