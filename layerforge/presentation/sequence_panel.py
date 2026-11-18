"""Placement sequence as a list: drag and drop reorders, a click selects the package."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QHBoxLayout, QListWidget, QListWidgetItem, QVBoxLayout, QWidget
from qt_controls_pyrs import CompactButton, HaloScrollBar

from layerforge.presentation.editor.controller import ORDER


class SequencePanel(QWidget):
    def __init__(self, session, controller, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.ctrl = controller
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        buttons = QHBoxLayout()
        self.auto = CompactButton("Automatic")
        self.auto.setToolTip("Lower left first, rows left to right, bottom to top")
        self.auto.clicked.connect(controller.auto_order)
        self.click = CompactButton("Click order")
        self.click.setToolTip("Click the packages in the editor in the new order (Esc restores)")
        self.click.clicked.connect(self._toggle_click_order)
        buttons.addWidget(self.auto)
        buttons.addWidget(self.click)
        layout.addLayout(buttons)

        self.list = QListWidget()
        self.list.setVerticalScrollBar(HaloScrollBar(self.list))
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        self.list.itemSelectionChanged.connect(self._on_list_selection)
        layout.addWidget(self.list, 1)

        self._updating = False
        session.projectChanged.connect(lambda *_: self.refresh())
        session.currentChanged.connect(lambda *_: self.refresh())
        controller.selectionChanged.connect(self._on_editor_selection)
        controller.modeChanged.connect(self._on_mode)
        self.refresh()

    def refresh(self) -> None:
        geo = self.ctrl.geo
        self._updating = True
        self.list.clear()
        if geo is not None:
            for index, pkg in enumerate(geo.pattern.packages):
                kind = "lying (0)" if pkg.orientation == 0 else "standing (90)"
                item = QListWidgetItem(f"{index + 1:>3}    {kind}")
                item.setData(Qt.ItemDataRole.UserRole, index)
                self.list.addItem(item)
        self._updating = False
        self._on_editor_selection(self.ctrl.selected())
        enabled = geo is not None and bool(geo.pattern.packages)
        self.auto.setEnabled(enabled)
        self.click.setEnabled(enabled)

    def _on_rows_moved(self, _parent, start, _end, _dest_parent, dest) -> None:
        if self._updating:
            return
        target = dest - 1 if dest > start else dest
        if target != start:
            self.ctrl.move_in_sequence(start, target)

    def _on_list_selection(self) -> None:
        if self._updating:
            return
        indexes = [item.data(Qt.ItemDataRole.UserRole) for item in self.list.selectedItems()]
        self.ctrl._select(indexes)

    def _on_editor_selection(self, indexes) -> None:
        self._updating = True
        wanted = set(indexes)
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole) in wanted)
        if indexes and self.list.count():
            self.list.scrollToItem(self.list.item(min(indexes)))
        self._updating = False

    def _toggle_click_order(self) -> None:
        if self.ctrl.mode == ORDER:
            self.ctrl.finish_order()
        else:
            self.ctrl.start_order()

    def _on_mode(self, mode: str) -> None:
        self.click.setText("Finish order" if mode == ORDER else "Click order")
