"""Pattern list: PatternId, name, verified state, package count, duplicate/similar badge and a
small preview; a larger preview pops up on hover. Manual order by drag and drop, or a
temporary view sorted by PatternId."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QStyle,
    QStyledItemDelegate, QToolButton, QVBoxLayout, QWidget
)
from qt_controls_pyrs import HaloScrollBar

from layerforge.domain import operations as ops
from layerforge.domain import validation as v
from layerforge.domain.export_model import is_verified
from layerforge.presentation import icons
from layerforge.presentation.preview import pattern_image
from layerforge.presentation.theme import ACCENT, ERROR, OK, WARNING

ROW_H = 58
THUMB = 46
POPUP = 260


class _Delegate(QStyledItemDelegate):
    def __init__(self, owner: "PatternList") -> None:
        super().__init__(owner)
        self.owner = owner

    def sizeHint(self, option, index) -> QSize:
        return QSize(160, ROW_H)

    def paint(self, painter: QPainter, option, index) -> None:
        session = self.owner.session
        uid = index.data(Qt.ItemDataRole.UserRole)
        try:
            pattern = session.project.pattern(uid)
        except (KeyError, AttributeError):
            return
        report = session.report(uid)
        rect = option.rect
        pal = option.palette
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            bg = QColor(ACCENT)
            bg.setAlpha(55 if selected else 22)
            painter.fillRect(rect, bg)
        if selected:
            painter.fillRect(QRect(rect.left(), rect.top(), 3, rect.height()), QColor(ACCENT))

        thumb = QRect(rect.left() + 8, rect.top() + (ROW_H - THUMB) // 2, THUMB, THUMB)
        image = pattern_image(pattern, THUMB, self.owner.devicePixelRatioF())
        painter.drawImage(thumb, image)

        text_x = thumb.right() + 10
        ink = pal.color(QPalette.ColorRole.Text)
        font = QFont(option.font)
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.1)
        painter.setFont(font)
        painter.setPen(ink)
        painter.drawText(QRect(text_x, rect.top() + 8, rect.width(), 20),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                         f"Pattern {pattern.pattern_id}" + (f"  ·  {pattern.name}" if pattern.name else ""))
        painter.setFont(option.font)
        dim = QColor(ink)
        dim.setAlpha(150)
        painter.setPen(dim)
        painter.drawText(QRect(text_x, rect.top() + 30, rect.width(), 18),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                         f"{len(pattern.packages)} packages")

        # Right edge: verified shield and, if any, one badge for the most important issue.
        x = rect.right() - 26
        if report is not None and report.valid and is_verified(pattern):
            painter.drawPixmap(QRect(x, rect.top() + 8, 18, 18), icons.tinted("verified", OK, 36))
        else:
            ring = QColor(ink)
            ring.setAlpha(90)
            painter.setPen(ring)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(x + 3, rect.top() + 11, 12, 12))
        badge, color = self._badge(report)
        if badge:
            painter.setPen(QColor(color))
            small = QFont(option.font)
            small.setPointSizeF(small.pointSizeF() * 0.85)
            small.setBold(True)
            painter.setFont(small)
            painter.drawText(QRect(rect.right() - 80, rect.top() + 30, 72, 18),
                             int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), badge)
        painter.restore()

    @staticmethod
    def _badge(report) -> tuple[str, str]:
        if report is None:
            return "", ""
        if report.has(v.DUPLICATE_GEOMETRY):
            return "DUPLICATE", ERROR
        if report.has(v.DUPLICATE_ID):
            return "ID TWICE", ERROR
        if report.has(v.DUPLICATE_NAME):
            return "NAME TWICE", ERROR
        if report.has(v.NAME_MISSING):
            return "NO NAME", ERROR
        if not report.valid:
            return "INVALID", ERROR
        if report.has(v.MIRROR_SIMILAR):
            return "MIRROR", WARNING
        return "", ""


class _Popup(QLabel):
    """Larger preview next to the hovered row."""

    def __init__(self, owner: QWidget) -> None:
        # Owned by the list (deleted with it) but shown as its own small window.
        super().__init__(owner, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMargin(10)
        self.setAutoFillBackground(True)

    def show_pattern(self, pattern, at: QPoint) -> None:
        from PyQt6.QtGui import QPixmap
        image = pattern_image(pattern, POPUP, self.devicePixelRatioF())
        self.setPixmap(QPixmap.fromImage(image))
        self.adjustSize()
        self.move(at)
        self.show()


class PatternList(QWidget):
    deleteRequested = pyqtSignal(int)

    def __init__(self, session, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(4)
        head = QHBoxLayout()
        self.caption = QLabel("Patterns")
        bold = self.caption.font()
        bold.setBold(True)
        self.caption.setFont(bold)
        head.addWidget(self.caption, 1)
        self.sort = QToolButton()
        self.sort.setCheckable(True)
        self.sort.setAutoRaise(True)
        self.sort.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sort.setIcon(icons.icon("sort_id"))
        self.sort.setToolTip("Temporarily sort by PatternId (the manual order is kept)")
        self.sort.toggled.connect(lambda _on: self.refresh(force=True))
        head.addWidget(self.sort)
        layout.addLayout(head)

        self.list = QListWidget()
        self.list.setItemDelegate(_Delegate(self))
        self.list.setVerticalScrollBar(HaloScrollBar(self.list))
        self.list.setMouseTracking(True)
        self.list.setUniformItemSizes(True)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        self.list.currentItemChanged.connect(self._on_current)
        self.list.viewport().installEventFilter(self)
        layout.addWidget(self.list, 1)

        self._popup = _Popup(self)
        self._hover_uid: int | None = None
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(350)
        self._hover_timer.timeout.connect(self._show_popup)
        self._order: list[int] = []
        self._updating = False

        session.projectChanged.connect(lambda *_: self.refresh())
        session.currentChanged.connect(self._select_uid)
        self.refresh()

    # ------------------------------------------------------------------ data

    def refresh(self, force: bool = False) -> None:
        project = self.session.project
        patterns = list(project.patterns) if project else []
        if self.sort.isChecked():
            patterns.sort(key=lambda p: p.pattern_id)
        order = [p.uid for p in patterns]
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop if self.sort.isChecked()
                                  else QAbstractItemView.DragDropMode.InternalMove)
        if order != self._order or force:
            self._updating = True
            self.list.clear()
            for uid in order:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, uid)
                item.setSizeHint(QSize(160, ROW_H))
                self.list.addItem(item)
            self._order = order
            self._updating = False
            self._select_uid(self.session.current_uid)
        else:
            self.list.viewport().update()     # same rows: repaint previews and badges
        verified = sum(1 for p in patterns if is_verified(p))
        self.caption.setText(f"Patterns  {verified}/{len(patterns)} verified" if patterns else "Patterns")

    def _select_uid(self, uid) -> None:
        self._updating = True
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.ItemDataRole.UserRole) == uid:
                self.list.setCurrentRow(row)
                break
        self._updating = False

    def _on_current(self, current, _previous) -> None:
        if not self._updating and current is not None:
            self.session.set_current(current.data(Qt.ItemDataRole.UserRole))

    def _on_rows_moved(self, _parent, start, _end, _dest_parent, dest) -> None:
        if self._updating:
            return
        uid = self._order[start]
        target = dest - 1 if dest > start else dest
        self._order = [self.list.item(r).data(Qt.ItemDataRole.UserRole) for r in range(self.list.count())]
        self.session.execute("Reorder pattern list", lambda p: ops.move_in_list(p, uid, target))

    # ----------------------------------------------------------------- hover

    def eventFilter(self, obj, event) -> bool:
        if obj is self.list.viewport():
            if event.type() == QEvent.Type.MouseMove:
                item = self.list.itemAt(event.position().toPoint())
                uid = item.data(Qt.ItemDataRole.UserRole) if item else None
                if uid != self._hover_uid:
                    self._hover_uid = uid
                    self._popup.hide()
                    if uid is not None:
                        self._hover_timer.start()
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress):
                self._hover_uid = None
                self._hover_timer.stop()
                self._popup.hide()
        return super().eventFilter(obj, event)

    def _show_popup(self) -> None:
        if self._hover_uid is None or self.session.project is None:
            return
        try:
            pattern = self.session.project.pattern(self._hover_uid)
        except KeyError:
            return
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.ItemDataRole.UserRole) == self._hover_uid:
                rect = self.list.visualItemRect(self.list.item(row))
                at = self.list.viewport().mapToGlobal(QPoint(self.list.viewport().width() + 8, rect.top()))
                self._popup.show_pattern(pattern, at)
                return

    def hideEvent(self, event) -> None:
        self._popup.hide()
        super().hideEvent(event)
