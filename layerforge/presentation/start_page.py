"""Start page: new, open, import a generated DB, recent projects."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qt_controls_pyrs import FrameButton, HaloButton

from layerforge import APP_NAME, APP_VERSION, BUILD_TIME
from layerforge.infrastructure.project_store import display_name


def _dimmed(label: QLabel) -> QLabel:
    palette = label.palette()
    palette.setColor(QPalette.ColorRole.WindowText, palette.color(QPalette.ColorRole.PlaceholderText))
    label.setPalette(palette)
    return label


class StartPage(QWidget):
    newRequested = pyqtSignal()
    openRequested = pyqtSignal()
    importRequested = pyqtSignal()
    recentRequested = pyqtSignal(str)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        outer = QHBoxLayout(self)
        outer.addStretch(1)
        column = QVBoxLayout()
        column.setSpacing(10)
        column.addStretch(2)
        title = QLabel(APP_NAME)
        font = title.font()
        font.setPointSizeF(font.pointSizeF() * 2.4)
        font.setWeight(300)
        title.setFont(font)
        column.addWidget(title)
        column.addWidget(_dimmed(QLabel("Pallet layer patterns from PDF to symbolic PLC parameters.")))
        column.addSpacing(24)
        for text, signal in (("New project", self.newRequested), ("Open project", self.openRequested),
                             ("Import generated TIA DB", self.importRequested)):
            button = HaloButton(text)
            button.UPPERCASE = False
            button.setMinimumWidth(340)
            button.clicked.connect(signal)
            column.addWidget(button)
        column.addSpacing(18)
        self.recent_title = QLabel("Recent projects")
        bold = self.recent_title.font()
        bold.setBold(True)
        self.recent_title.setFont(bold)
        column.addWidget(self.recent_title)
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(2)
        column.addLayout(self.recent_box)
        column.addStretch(3)
        column.addWidget(_dimmed(QLabel(f"Version {APP_VERSION}" + (f" · built {BUILD_TIME}" if BUILD_TIME else ""))),
                         0, Qt.AlignmentFlag.AlignHCenter)
        outer.addLayout(column)
        outer.addStretch(1)
        self.refresh()

    def refresh(self) -> None:
        while self.recent_box.count():
            widget = self.recent_box.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        recent = self.settings.recent_projects()
        self.recent_title.setVisible(bool(recent))
        for path in recent:
            button = FrameButton(display_name(path))
            button.setToolTip(path)
            button.setMinimumWidth(340)
            button.clicked.connect(lambda _c=False, p=path: self.recentRequested.emit(p))
            self.recent_box.addWidget(button)
