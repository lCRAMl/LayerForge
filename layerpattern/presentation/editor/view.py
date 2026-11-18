"""QGraphicsView of the editor: navigation, grid and the screen-space overlay.

Overlay text (dimensions, sequence numbers, guides) is painted in viewport pixels in
`drawForeground`, so it stays crisp and readable at every zoom level and costs no
scene items.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PyQt6.QtWidgets import QFrame, QGraphicsView

from layerpattern.domain.geometry import overhang
from layerpattern.domain.linear import LinearForm
from layerpattern.presentation.editor.controller import ADD, ORDER, PLACE, EditorController
from layerpattern.presentation.theme import editor_colors

ZOOM_MIN, ZOOM_MAX = 0.005, 20.0


def fmt_mm(value: float) -> str:
    """At most one decimal, none when the value is whole."""
    rounded = round(value, 1)
    return f"{rounded:.0f}" if abs(rounded - round(rounded)) < 1e-9 else f"{rounded:.1f}"


class EditorView(QGraphicsView):
    def __init__(self, controller: EditorController, parent=None) -> None:
        super().__init__(controller.scene, parent)
        self.ctrl = controller
        controller.view = self
        controller.overlayChanged.connect(self.viewport().update)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        # The overlay depends on the whole view; partial updates would leave fragments.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setTransform(QTransform.fromScale(0.5, -0.5))
        self._pan: QPointF | None = None

    # ------------------------------------------------------------ navigation

    def zoom(self) -> float:
        return self.transform().m11()

    def fit_rect(self, rect: QRectF) -> None:
        if rect.isEmpty() or self.viewport().width() < 10:
            return
        margin = 90.0                      # room for the dimension lines
        sx = (self.viewport().width() - 2 * margin) / rect.width()
        sy = (self.viewport().height() - 2 * margin) / rect.height()
        z = max(ZOOM_MIN, min(ZOOM_MAX, min(sx, sy)))
        self.setTransform(QTransform.fromScale(z, -z))
        self.centerOn(rect.center())
        self.viewport().update()

    def wheelEvent(self, event) -> None:
        factor = 1.0015 ** event.angleDelta().y()
        z = self.zoom()
        factor = max(ZOOM_MIN / z, min(ZOOM_MAX / z, factor))
        # Zoom about the cursor: the scene point under it stays put.
        anchor = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        moved = self.mapToScene(event.position().toPoint())
        self.translate(moved.x() - anchor.x(), moved.y() - anchor.y())
        self.viewport().update()

    def cursor_scene_pos(self) -> QPointF:
        return self.mapToScene(self.mapFromGlobal(QCursor.pos()))

    # ----------------------------------------------------------------- mouse

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if self.ctrl.press(self.mapToScene(event.position().toPoint()), event.button(),
                           event.modifiers()):
            return
        if event.button() == Qt.MouseButton.LeftButton and self.ctrl.mode == "select":
            if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.ctrl._select([])
            super().mousePressEvent(event)      # rubber band

    def mouseMoveEvent(self, event) -> None:
        if self._pan is not None:
            delta = event.position() - self._pan
            self._pan = event.position()
            z = self.zoom()
            self.translate(delta.x() / z, -delta.y() / z)
            self.viewport().update()
            return
        self.ctrl.move(self.mapToScene(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton and self._pan is not None:
            self._pan = None
            self.viewport().unsetCursor()
            return
        self.ctrl.release(self.mapToScene(event.position().toPoint()))
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        for ghost in self.ctrl.ghosts:
            ghost.setVisible(False)
        super().leaveEvent(event)

    # ------------------------------------------------------------- background

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        colors = editor_colors()
        painter.fillRect(rect, colors.background)
        # Zoom-adaptive grid without functional meaning: the smallest 1-2-5 step that
        # keeps lines at least 12 px apart.
        z = self.zoom()
        step = 1.0
        while step * z < 12:
            for k in (2, 2.5, 2):
                step *= k
                if step * z >= 12:
                    break
        major = step * 5
        painter.save()
        for spacing, color in ((step, colors.grid_minor), (major, colors.grid_major)):
            pen = QPen(color, 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            x = math.floor(rect.left() / spacing) * spacing
            lines = []
            while x <= rect.right():
                lines.append(QLineF(x, rect.top(), x, rect.bottom()))
                x += spacing
            y = math.floor(rect.top() / spacing) * spacing
            while y <= rect.bottom():
                lines.append(QLineF(rect.left(), y, rect.right(), y))
                y += spacing
            painter.drawLines(lines)
        painter.restore()

    # ---------------------------------------------------------------- overlay

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        geo = self.ctrl.geo
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if geo is None:
            self._empty_hint(painter, "No pattern selected.")
        elif not geo.pattern.packages:
            self._empty_hint(painter, "Empty pattern - use Add Package to place the first one.")
        elif not geo.valid_dims:
            self._empty_hint(painter, "Invalid example values - check KL, KB and D.")
        else:
            Overlay(self, painter).paint()
        painter.restore()

    def _empty_hint(self, painter: QPainter, text: str) -> None:
        painter.setPen(editor_colors().dimension)
        painter.drawText(QRectF(self.viewport().rect()), int(Qt.AlignmentFlag.AlignCenter), text)


class Overlay:
    """Dimensions, labels and guides for one paint pass, in viewport pixels."""

    def __init__(self, view: EditorView, painter: QPainter) -> None:
        self.view = view
        self.p = painter
        self.ctrl = view.ctrl
        self.geo = view.ctrl.geo
        self.colors = editor_colors()
        self.numeric = self.ctrl.display["numeric"]
        self.font = QFont(view.font())
        self.fm = QFontMetricsF(self.font)
        self.map = view.viewportTransform().map

    def pt(self, x: float, y: float) -> QPointF:
        return self.map(QPointF(x, y))

    def label(self, form: LinearForm | None, value: float) -> str:
        if self.numeric or form is None:
            return f"{fmt_mm(value)}"
        return form.text("·")

    # --- primitives -----------------------------------------------------

    def text_box(self, centre: QPointF, text: str, color: QColor, angle: float = 0.0,
                 bold: bool = False) -> None:
        font = QFont(self.font)
        font.setBold(bold)
        fm = QFontMetricsF(font)
        w, h = fm.horizontalAdvance(text) + 8, fm.height() + 2
        self.p.save()
        self.p.translate(centre)
        self.p.rotate(angle)
        box = QRectF(-w / 2, -h / 2, w, h)
        bg = QColor(self.colors.background)
        bg.setAlpha(215)
        self.p.setPen(Qt.PenStyle.NoPen)
        self.p.setBrush(bg)
        self.p.drawRoundedRect(box, 3, 3)
        self.p.setFont(font)
        self.p.setPen(color)
        self.p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), text)
        self.p.restore()

    def arrow(self, tip: QPointF, direction: QPointF, color: QColor) -> None:
        size = 7.0
        nx, ny = -direction.y(), direction.x()
        base = tip - direction * size
        poly = QPolygonF([tip, base + QPointF(nx, ny) * 2.6, base - QPointF(nx, ny) * 2.6])
        self.p.setPen(Qt.PenStyle.NoPen)
        self.p.setBrush(color)
        self.p.drawPolygon(poly)

    def dimension(self, a_scene: QPointF, b_scene: QPointF, offset: float, text: str,
                  color: QColor | None = None) -> None:
        """Dimension between two scene points, `offset` pixels to the side."""
        color = color or self.colors.dimension
        a, b = self.map(a_scene), self.map(b_scene)
        length = math.hypot(b.x() - a.x(), b.y() - a.y())
        if length < 6:
            return
        d = QPointF((b.x() - a.x()) / length, (b.y() - a.y()) / length)
        n = QPointF(-d.y(), d.x())
        a2, b2 = a + n * offset, b + n * offset
        pen = QPen(color, 1)
        self.p.setPen(pen)
        sign = 1 if offset >= 0 else -1
        self.p.drawLine(a + n * (3 * sign), a2 + n * (4 * sign))
        self.p.drawLine(b + n * (3 * sign), b2 + n * (4 * sign))
        self.p.drawLine(a2, b2)
        self.arrow(a2, d * -1, color)
        self.arrow(b2, d, color)
        angle = math.degrees(math.atan2(d.y(), d.x()))
        if angle > 90 or angle < -90:
            angle += 180
        text_w = self.fm.horizontalAdvance(text) + 8
        mid = (a2 + b2) / 2
        if text_w > length - 16:
            # Too short for the text inside: put it beside the line.
            mid = mid + n * (sign * (self.fm.height() / 2 + 4))
        self.text_box(mid, text, color, angle)

    # --- content ----------------------------------------------------------

    def paint(self) -> None:
        geo, ctrl = self.geo, self.ctrl
        display = ctrl.display
        dims = geo.pattern.dims
        bounds = QRectF()
        for box in geo.boxes:
            bounds = bounds.united(box)
        if display["bbox"]:
            pen = QPen(self.colors.dimension, 1, Qt.PenStyle.DashLine)
            self.p.setPen(pen)
            self.p.setBrush(Qt.BrushStyle.NoBrush)
            self.p.drawRect(QRectF(self.pt(bounds.left(), bounds.top()), self.pt(bounds.right(), bounds.bottom())).normalized())

        self._package_marks(display)

        # Pattern size: below and left. Pallet size: above and right (always numeric).
        # Offsets are in screen pixels along the left-hand normal of a -> b.
        self.dimension(QPointF(bounds.left(), bounds.top()), QPointF(bounds.right(), bounds.top()),
                       34, self.label(geo.width, bounds.width()))
        self.dimension(QPointF(bounds.left(), bounds.top()), QPointF(bounds.left(), bounds.bottom()),
                       -34, self.label(geo.height, bounds.height()))
        if display["pallet"]:
            pallet = ctrl.pallet.rect()
            top = max(pallet.bottom(), bounds.bottom())
            right = max(pallet.right(), bounds.right())
            self.dimension(QPointF(pallet.left(), top), QPointF(pallet.right(), top),
                           -26, f"Pallet {fmt_mm(dims.pallet_x)}", self.colors.pallet_text)
            self.dimension(QPointF(right, pallet.top()), QPointF(right, pallet.bottom()),
                           26, f"Pallet {fmt_mm(dims.pallet_y)}", self.colors.pallet_text)
            if display["overhang"]:
                self._overhang(bounds, pallet)

        self._centre_mark()
        selected = ctrl.selected()
        if len(selected) == 1 and ctrl.mode not in (ADD, PLACE, ORDER):
            self._selected_package(selected[0])
        self._guides()

    def _package_marks(self, display) -> None:
        geo, ctrl = self.geo, self.ctrl
        ordering = ctrl.mode == ORDER
        for item in ctrl.items:
            r = item.sceneBoundingRect()
            tl, br = self.pt(r.left(), r.bottom()), self.pt(r.right(), r.top())
            screen = QRectF(tl, br).normalized()
            centre = screen.center()
            if display["orientation"] and min(screen.width(), screen.height()) > 18:
                # A thin line along KL marks the BaseOrientation.
                color = QColor(self.colors.package_edge)
                color.setAlpha(120)
                self.p.setPen(QPen(color, 1))
                if item.orientation == 0:
                    half = screen.width() * 0.32
                    self.p.drawLine(centre - QPointF(half, 0), centre + QPointF(half, 0))
                else:
                    half = screen.height() * 0.32
                    self.p.drawLine(centre - QPointF(0, half), centre + QPointF(0, half))
            if display["centres"]:
                self.p.setPen(QPen(self.colors.dimension, 1))
                self.p.drawLine(centre - QPointF(4, 0), centre + QPointF(4, 0))
                self.p.drawLine(centre - QPointF(0, 4), centre + QPointF(0, 4))
            if ordering:
                if item.index in ctrl.order:
                    self.text_box(centre, str(ctrl.order.index(item.index) + 1),
                                  self.colors.guide, bold=True)
                else:
                    self.text_box(centre, "?", self.colors.dimension)
            elif display["sequence"] and min(screen.width(), screen.height()) > 14:
                self.p.setPen(self.colors.package_text)
                font = QFont(self.font)
                font.setPointSizeF(max(7.0, min(14.0, min(screen.width(), screen.height()) / 4)))
                font.setBold(True)
                self.p.setFont(font)
                offset = QPointF(0, -font.pointSizeF() * 0.9) if display["orientation"] else QPointF()
                self.p.drawText(QRectF(centre.x() - 30, centre.y() - 12, 60, 24) .translated(offset),
                                int(Qt.AlignmentFlag.AlignCenter), str(item.index + 1))
        self.p.setFont(self.font)

    def _centre_mark(self) -> None:
        c = self.pt(0.0, 0.0)
        color = self.colors.selected
        self.p.setPen(QPen(color, 1.2))
        self.p.setBrush(Qt.BrushStyle.NoBrush)
        self.p.drawEllipse(c, 5, 5)
        self.p.drawLine(c - QPointF(10, 0), c + QPointF(10, 0))
        self.p.drawLine(c - QPointF(0, 10), c + QPointF(0, 10))

    def _selected_package(self, index: int) -> None:
        geo = self.geo
        dragging = self.ctrl.drag is not None and self.ctrl.drag.active
        # While dragging, the model position is stale: measure the moving item instead.
        box = self.ctrl.items[index].sceneBoundingRect() if dragging else geo.boxes[index]
        pkg = geo.pattern.packages[index]
        width_form = (pkg.half_width() * 2)
        height_form = (pkg.half_height() * 2)
        accent = self.colors.selected
        self.dimension(QPointF(box.left(), box.bottom()), QPointF(box.right(), box.bottom()),
                       -14, self.label(width_form, box.width()), accent)
        self.dimension(QPointF(box.right(), box.top()), QPointF(box.right(), box.bottom()),
                       14, self.label(height_form, box.height()), accent)
        if dragging:
            return                 # the relation is only known on release (see guide label)
        # Relative centre from the pattern centre, as two legs.
        rx, ry = geo.relative[index]
        cx, cy = box.center().x(), box.center().y()
        origin, corner, centre = self.pt(0, 0), self.pt(cx, 0), self.pt(cx, cy)
        pen = QPen(accent, 1, Qt.PenStyle.DashLine)
        self.p.setPen(pen)
        self.p.drawLine(origin, corner)
        self.p.drawLine(corner, centre)
        if abs(cx) > 1e-6:
            self.text_box((origin + corner) / 2 + QPointF(0, 12), "X = " + self.label(rx, cx), accent)
        if abs(cy) > 1e-6:
            # Beside the vertical leg, away from the sequence number in the package centre.
            side = -(self.fm.height() / 2 + 10)
            self.text_box((corner + centre) / 2 + QPointF(side, 0), "Y = " + self.label(ry, cy), accent, -90)
        # Neighbour gaps: exactly D by definition of "neighbour".
        dims = geo.pattern.dims
        gap_text = "D" if not self.numeric else fmt_mm(dims.d)
        for i, j in geo.neighbours:
            if index not in (i, j):
                continue
            a, b = geo.boxes[i], geo.boxes[j]
            if a.right() <= b.left() or b.right() <= a.left():
                x = (min(a.right(), b.right()) + max(a.left(), b.left())) / 2
                y = (max(a.top(), b.top()) + min(a.bottom(), b.bottom())) / 2
            else:
                x = (max(a.left(), b.left()) + min(a.right(), b.right())) / 2
                y = (min(a.bottom(), b.bottom()) + max(a.top(), b.top())) / 2
            self.text_box(self.pt(x, y), gap_text, self.colors.guide)

    def _overhang(self, bounds: QRectF, pallet: QRectF) -> None:
        ox, oy = overhang(self.geo.pattern.packages, self.geo.pattern.dims)
        color = self.colors.uncertain
        if ox > 0:
            self.dimension(QPointF(pallet.right(), 0), QPointF(bounds.right(), 0), 0,
                           f"+{fmt_mm(float(ox))}", color)
        if oy > 0:
            self.dimension(QPointF(0, pallet.bottom()), QPointF(0, bounds.bottom()), 0,
                           f"+{fmt_mm(float(oy))}", color)

    def _guides(self) -> None:
        ctrl = self.ctrl
        if not ctrl.display["guides"]:
            return
        if ctrl.drag is not None and ctrl.drag.active:
            snaps, mover = (ctrl.drag.snap_x, ctrl.drag.snap_y), ctrl.items[ctrl.drag.anchor]
        elif ctrl.mode in (ADD, PLACE) and ctrl.ghosts and ctrl.ghosts[0].isVisible():
            snaps, mover = ctrl.ghost_snap, ctrl.ghosts[0]
        else:
            return
        color = self.colors.guide
        pen = QPen(color, 1, Qt.PenStyle.DashLine)
        vp = QRectF(self.view.viewport().rect())
        r = mover.sceneBoundingRect()
        for axis, cand in zip("xy", snaps):
            if cand is None:
                continue
            ref = ctrl.items[cand.reference].sceneBoundingRect()
            self.p.setPen(QPen(color, 1.5))
            self.p.setBrush(Qt.BrushStyle.NoBrush)
            self.p.drawRect(QRectF(self.pt(ref.left(), ref.bottom()), self.pt(ref.right(), ref.top())).normalized())
            self.p.setPen(pen)
            if axis == "x":
                x = {"lo": r.left(), "hi": r.right(), "c": r.center().x()}[cand.feature]
                sx = self.pt(x, 0).x()
                self.p.drawLine(QPointF(sx, vp.top()), QPointF(sx, vp.bottom()))
            else:
                y = {"lo": r.top(), "hi": r.bottom(), "c": r.center().y()}[cand.feature]
                sy = self.pt(0, y).y()
                self.p.drawLine(QPointF(vp.left(), sy), QPointF(vp.right(), sy))
        texts = [c.text for c in snaps if c is not None]
        if texts:
            anchor = self.pt(r.right(), r.bottom()) + QPointF(14, -14)
            text = " · ".join(texts)
            self.text_box(anchor + QPointF(self.fm.horizontalAdvance(text) / 2, 0), text, color)
