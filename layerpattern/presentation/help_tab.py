"""Offline help: local HTML in a QTextBrowser (no web engine, loads instantly)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

HELP_FILE = Path(__file__).resolve().parents[1] / "resources" / "help" / "index.html"


class HelpTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        layout.addWidget(self.browser)
        self._loaded = False

    def show_topic(self, anchor: str = "") -> None:
        if not self._loaded:
            # Loaded on first use: the help is never needed at start-up.
            self.browser.setSource(QUrl.fromLocalFile(str(HELP_FILE)))
            self._loaded = True
        if anchor:
            self.browser.scrollToAnchor(anchor)
