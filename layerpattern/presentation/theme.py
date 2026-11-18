"""Application palette (dark or light) and the editor colours that go with it.

The QtControlsPyRS widgets take their colours from the palette, so setting it once
before any window is built themes the whole application.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QStyleFactory, QWidget

ACCENT = "#5a8cff"
WARNING = "#f0b429"
ERROR = "#ff4d4d"
OK = "#3ecf8e"


@dataclass(frozen=True)
class EditorColors:
    background: QColor
    grid_minor: QColor
    grid_major: QColor
    pallet_fill: QColor
    pallet_edge: QColor
    pallet_text: QColor
    package_fill: QColor
    package_edge: QColor
    package_text: QColor
    selected: QColor
    invalid: QColor
    uncertain: QColor
    dimension: QColor
    guide: QColor
    preview_fill: QColor


DARK = EditorColors(
    background=QColor("#15181d"),
    grid_minor=QColor(255, 255, 255, 10),
    grid_major=QColor(255, 255, 255, 22),
    pallet_fill=QColor("#2b2620"),
    pallet_edge=QColor("#6d5c43"),
    pallet_text=QColor("#c9ad80"),
    package_fill=QColor("#2f4a66"),
    package_edge=QColor("#8db3dc"),
    package_text=QColor("#e8eef6"),
    selected=QColor(ACCENT),
    invalid=QColor(ERROR),
    uncertain=QColor(WARNING),
    dimension=QColor("#b9c3cf"),
    guide=QColor("#43d1c0"),
    preview_fill=QColor("#4a6f96"),
)

LIGHT = EditorColors(
    background=QColor("#f7f8fa"),
    grid_minor=QColor(0, 0, 0, 12),
    grid_major=QColor(0, 0, 0, 26),
    pallet_fill=QColor("#ece2cf"),
    pallet_edge=QColor("#a58c62"),
    pallet_text=QColor("#7a5f32"),
    package_fill=QColor("#c9daee"),
    package_edge=QColor("#3d6690"),
    package_text=QColor("#14263a"),
    selected=QColor("#2f6bff"),
    invalid=QColor("#e23b3b"),
    uncertain=QColor("#c98a00"),
    dimension=QColor("#4b5563"),
    guide=QColor("#0f9e8e"),
    preview_fill=QColor("#7da3cc"),
)

_current = DARK


def editor_colors() -> EditorColors:
    return _current


def apply_theme(app: QApplication, mode: str) -> None:
    global _current
    app.setStyle(QStyleFactory.create("Fusion"))
    dark = mode != "light"
    _current = DARK if dark else LIGHT
    p = QPalette()
    if dark:
        roles = {
            "Window": "#1e1f22", "WindowText": "#e6e6e6", "Base": "#17181a",
            "AlternateBase": "#222326", "Text": "#e6e6e6", "Button": "#2a2b2f",
            "ButtonText": "#e6e6e6", "ToolTipBase": "#2a2b2f", "ToolTipText": "#e6e6e6",
            "Highlight": ACCENT, "HighlightedText": "#0b0b0b", "PlaceholderText": "#7d8590",
            "Link": ACCENT, "Mid": "#3a3b40", "Midlight": "#323338", "Dark": "#121315",
            "Shadow": "#000000", "Light": "#3d3e43",
        }
    else:
        roles = {
            "Window": "#f3f4f6", "WindowText": "#1d2127", "Base": "#ffffff",
            "AlternateBase": "#f0f2f5", "Text": "#1d2127", "Button": "#e9ebef",
            "ButtonText": "#1d2127", "ToolTipBase": "#ffffff", "ToolTipText": "#1d2127",
            "Highlight": "#2f6bff", "HighlightedText": "#ffffff", "PlaceholderText": "#8a919c",
            "Link": "#2f6bff", "Mid": "#c9cdd4", "Midlight": "#dde0e5", "Dark": "#a9aeb7",
            "Shadow": "#6b7280", "Light": "#ffffff",
        }
    for role, color in roles.items():
        p.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in ("WindowText", "Text", "ButtonText"):
        p.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role),
                   QColor("#6b7078" if dark else "#a0a6b0"))
    app.setPalette(p)


def dark_title_bar(window: QWidget, dark: bool) -> None:
    """Windows 10/11 draw the title bar light unless asked; a dark app looks broken then."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        value = ctypes.c_int(1 if dark else 0)
        hwnd = int(window.winId())
        for attribute in (20, 19):    # DWMWA_USE_IMMERSIVE_DARK_MODE (new / pre-20H1)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value),
                                                          ctypes.sizeof(value)) == 0:
                break
    except (AttributeError, OSError):
        pass
