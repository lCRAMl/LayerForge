"""Scene items. They only paint; every decision is made by the controller.

Scene units are millimetres with Y pointing up (the view flips Y). Pens are cosmetic,
so line widths stay constant on screen at every zoom level.
"""

from __future__ import annotations

from PyQt6.QtCore import QLineF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsItem

from layerforge.presentation.theme import editor_colors

# Visual states of a package
NORMAL, INVALID, UNCERTAIN = 0, 1, 2


def _pen(color: QColor, width: float = 1.0, style=Qt.PenStyle.SolidLine) -> QPen:
    pen = QPen(color, width, style)
    pen.setCosmetic(True)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    return pen


class PackageItem(QGraphicsItem):
    """One package. `index` is its position in `Pattern.packages` (0-based, internal only)."""

    def __init__(self, index: int, width: float, height: float, orientation: int,
                 ghost: bool = False) -> None:
        super().__init__()
        self.index = index
        self.orientation = orientation
        self.state = NORMAL
        self.ghost = ghost
        self._rect = QRectF()
        self.set_size(width, height)
        if not ghost:
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(10 if not ghost else 20)

    def set_size(self, width: float, height: float) -> None:
        rect = QRectF(-width / 2, -height / 2, width, height)
        if rect != self._rect:
            self.prepareGeometryChange()
            self._rect = rect

    def rect(self) -> QRectF:
        return self._rect

    def set_state(self, state: int) -> None:
        if state != self.state:
            self.state = state
            self.update()

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        colors = editor_colors()
        selected = self.isSelected()
        fill = QColor(colors.package_fill)
        if self.ghost:
            fill.setAlpha(110)
        painter.setBrush(fill)
        edge = colors.selected if selected else colors.package_edge
        width = 2.0 if selected else 1.0
        if self.state == INVALID:
            edge, width = colors.invalid, 2.0
        painter.setPen(_pen(edge, width, Qt.PenStyle.DashLine if self.ghost else Qt.PenStyle.SolidLine))
        painter.drawRect(self._rect)
        if self.state == INVALID:
            hatch = QColor(colors.invalid)
            hatch.setAlpha(60)
            brush = QBrush(hatch, Qt.BrushStyle.BDiagPattern)
            painter.fillRect(self._rect, brush)
        elif self.state == UNCERTAIN:
            painter.setPen(_pen(colors.uncertain, 2.0, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rect)
        if selected and not self.ghost:
            glow = QColor(colors.selected)
            glow.setAlpha(45)
            painter.fillRect(self._rect, glow)


class PalletItem(QGraphicsItem):
    """Numeric reference below the packages: centred, not selectable."""

    def __init__(self) -> None:
        super().__init__()
        self._rect = QRectF()
        self.setZValue(-10)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def set_size(self, width: float, height: float) -> None:
        rect = QRectF(-width / 2, -height / 2, width, height)
        if rect != self._rect:
            self.prepareGeometryChange()
            self._rect = rect

    def rect(self) -> QRectF:
        return self._rect

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        colors = editor_colors()
        painter.setBrush(colors.pallet_fill)
        painter.setPen(_pen(colors.pallet_edge, 1.0))
        painter.drawRect(self._rect)
        # Deck boards, faintly: tells "pallet" at a glance without competing.
        board = QColor(colors.pallet_edge)
        board.setAlpha(55)
        painter.setPen(_pen(board, 1.0))
        r = self._rect
        steps = 7
        painter.drawLines([QLineF(r.left(), r.top() + r.height() * k / steps,
                                  r.right(), r.top() + r.height() * k / steps) for k in range(1, steps)])
