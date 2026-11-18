"""Monochrome line icons as inline SVG.

They are drawn in black; HaloCommandBar tints them to the text colour of the theme.
Other places (menus, lists) use `icon(name, color)` to get a tinted copy directly.
"""

from __future__ import annotations

from functools import lru_cache

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap

_S = 'fill="none" stroke="black" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'

PATHS = {
    "new": f'<path {_S} d="M6 3h8l4 4v14H6z M14 3v4h4 M12 11v6 M9 14h6"/>',
    "open": f'<path {_S} d="M3 7h6l2 2h10v10H3z M3 12h18"/>',
    "save": f'<path {_S} d="M5 4h11l3 3v13H5z M8 4v5h7V4 M8 20v-6h8v6"/>',
    "save_as": f'<path {_S} d="M5 4h11l3 3v6 M5 4v16h7 M8 4v5h7V4 M15 20l5-5 2 2-5 5h-2z"/>',
    "import_db": f'<path {_S} d="M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z M4 6v12c0 1.7 3.6 3 8 3 M20 6v6 M16 17h6 M19 14l3 3-3 3"/>',
    "undo": f'<path {_S} d="M9 7L5 11l4 4 M5 11h9a5 5 0 0 1 0 10h-3"/>',
    "redo": f'<path {_S} d="M15 7l4 4-4 4 M19 11h-9a5 5 0 0 0 0 10h3"/>',
    "delete": f'<path {_S} d="M4 7h16 M9 7V4h6v3 M6 7l1 13h10l1-13 M10 11v6 M14 11v6"/>',
    "pattern_new": f'<path {_S} d="M3 5h8v5H3z M3 12h5v8H3z M10 12h4v4 M17 14v6 M14 17h6"/>',
    "pattern_delete": f'<path {_S} d="M3 5h8v5H3z M3 12h5v8H3z M14 14l6 6 M20 14l-6 6"/>',
    "rotate_pattern": f'<path {_S} d="M4 12a8 8 0 1 0 2.3-5.6 M4 3v4h4 M10 10h5v3h-5z M10 13h3v4h-3z"/>',
    "change_id": f'<path {_S} d="M4 8h16v10H4z M8 11v4 M11 11v4h2a2 2 0 0 0 0-4z"/>',
    "add_package": f'<path {_S} d="M3 8h13v9H3z M19 3v6 M16 6h6"/>',
    "duplicate": f'<path {_S} d="M8 8h12v9H8z M4 4h12v2 M4 4v9h2"/>',
    "rotate_package": f'<path {_S} d="M7 6h7v12H7z M17 8a6 6 0 0 1 0 8 M17 16v-3 M17 16h3"/>',
    "auto_order": f'<path {_S} d="M4 18h4v-4H4z M10 18h4v-4h-4z M16 18h4v-4h-4z M4 6h16 M16 3l4 3-4 3"/>',
    "click_order": f'<path {_S} d="M5 3l12 7-5 1.5 3 6-2 1-3-6-4 3z"/>',
    "fit": f'<path {_S} d="M4 9V4h5 M15 4h5v5 M20 15v5h-5 M9 20H4v-5 M9 9h6v6H9z"/>',
    "fit_pallet": f'<path {_S} d="M4 9V4h5 M15 4h5v5 M20 15v5h-5 M9 20H4v-5 M7 8h10v8H7z M10 11h4v2h-4z"/>',
    "numeric": f'<path {_S} d="M4 8l2-2v12 M10 8a2 2 0 0 1 4 0c0 2-4 4-4 10h4 M17 6h3l-2 4a3 3 0 1 1-2 5"/>',
    "verify": f'<path {_S} d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z M8.5 12l2.5 2.5 4.5-5"/>',
    "export": f'<path {_S} d="M12 15V3 M8 7l4-4 4 4 M4 13v7h16v-7"/>',
    "options": f'<path {_S} d="M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z M12 2v3 M12 19v3 M2 12h3 M19 12h3 M4.9 4.9l2.1 2.1 M17 17l2.1 2.1 M4.9 19.1L7 17 M17 7l2.1-2.1"/>',
    "help": f'<path {_S} d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .8-1 1.5V14 M12 17v.3"/>',
    "pdf_import": f'<path {_S} d="M6 3h8l4 4v14H6z M14 3v4h4 M9 13h6 M12 10v6"/>',
    "recognize_page": f'<path {_S} d="M6 3h8l4 4v14H6z M14 3v4h4 M9 11h3v3H9z M13 11h2v3h-2z M9 15h6v2H9z"/>',
    "recognize_region": f'<path {_S} d="M4 7V4h3 M17 4h3v3 M20 17v3h-3 M7 20H4v-3 M8 8h4v4H8z M13 8h3v4h-3z M8 13h8v3H8z"/>',
    "accept": f'<path {_S} d="M4 12l5 5L20 6"/>',
    "accept_all": f'<path {_S} d="M2 12l5 5L18 6 M9 17l1 1L22 6"/>',
    "source_view": f'<path {_S} d="M6 3h8l4 4v14H6z M14 3v4h4 M10 13a2 2 0 1 0 4 0 2 2 0 1 0-4 0 M13.5 14.5L16 17"/>',
    "relink": f'<path {_S} d="M10 14a4 4 0 0 0 5.6 0l3-3a4 4 0 0 0-5.6-5.6l-1 1 M14 10a4 4 0 0 0-5.6 0l-3 3a4 4 0 0 0 5.6 5.6l1-1"/>',
    "sort_id": f'<path {_S} d="M6 4v16 M3 17l3 3 3-3 M13 5h3v6 M13 11h6 M13 14h5l-5 6h5"/>',
    "cancel": f'<path {_S} d="M6 6l12 12 M18 6L6 18"/>',
    "swap": f'<path {_S} d="M4 8h14 M15 5l3 3-3 3 M20 16H6 M9 13l-3 3 3 3"/>',
    "verified": '<path fill="black" d="M12 2l8 3.5v6c0 5.2-3.4 8.8-8 10.5-4.6-1.7-8-5.3-8-10.5v-6z"/>'
                '<path fill="none" stroke="white" stroke-width="2" stroke-linecap="round" '
                'stroke-linejoin="round" d="M8.3 12.2l2.6 2.6 4.8-5"/>',
}


@lru_cache(maxsize=None)
def _pixmap(name: str, size: int) -> QPixmap:
    from PyQt6.QtSvg import QSvgRenderer

    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{PATHS[name]}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode("ascii")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


@lru_cache(maxsize=None)
def icon(name: str) -> QIcon:
    """Black template icon; HaloCommandBar tints it."""
    result = QIcon()
    for size in (16, 24, 32, 48):
        result.addPixmap(_pixmap(name, size))
    return result


def tinted(name: str, color: QColor | str, size: int = 32) -> QPixmap:
    """Coloured copy, for places that do not tint by themselves."""
    source = _pixmap(name, size)
    result = QPixmap(source.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.drawPixmap(0, 0, source)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(result.rect(), QColor(color))
    painter.end()
    return result
