"""Editor logic: selection, tools, dragging with symbolic snapping, sequence editing.

Items never move themselves. During a drag the controller moves them visually (GUI
thread, no project change); on release it resolves exact relations and commits ONE
undoable command through the session. The scene is updated incrementally from the
resulting project: same package count -> items are moved, otherwise rebuilt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QGraphicsScene

from layerpattern.domain import operations as ops
from layerpattern.domain import snapping
from layerpattern.domain import validation as v
from layerpattern.domain.geometry import extent, neighbour_pairs, normalized, rects
from layerpattern.domain.linear import LinearForm
from layerpattern.domain.model import Package, Pattern
from layerpattern.domain.sequence import auto_order, reordered
from layerpattern.presentation.editor.items import INVALID, NORMAL, PackageItem, PalletItem

SNAP_PX = 14          # snap radius on screen while dragging
DRAG_START_PX = 4

SELECT, ADD, PLACE, ORDER = "select", "add", "place", "order"

DISPLAY_DEFAULTS = {
    "pallet": True, "centres": False, "guides": True, "sequence": True,
    "orientation": True, "bbox": False, "overhang": False, "numeric": False,
}

_GEOMETRY_ISSUES = (v.OVERLAP, v.CLEARANCE, v.DISCONNECTED)


def _mm(form: LinearForm, dims) -> float:
    return float(form.value(dims.kl, dims.kb, dims.d))


@dataclass
class Geometry:
    """Everything the view needs about the current pattern, computed once per change."""

    pattern: Pattern
    cx: float = 0.0                      # bounding-box centre in the stored frame [mm]
    cy: float = 0.0
    boxes: list[QRectF] = field(default_factory=list)   # scene rects (centre at origin)
    relative: list[tuple[LinearForm, LinearForm]] = field(default_factory=list)
    width: LinearForm | None = None
    height: LinearForm | None = None
    neighbours: list[tuple[int, int]] = field(default_factory=list)
    invalid: set[int] = field(default_factory=set)

    @property
    def valid_dims(self) -> bool:
        return self.pattern.dims.is_valid()


@dataclass
class Drag:
    anchor: int
    start: QPointF                       # scene position of the press
    origins: dict[int, QPointF]          # scene centre of each moving item at press
    cand_x: list = field(default_factory=list)
    cand_y: list = field(default_factory=list)
    active: bool = False
    snap_x: snapping.Candidate | None = None
    snap_y: snapping.Candidate | None = None


class EditorController(QObject):
    selectionChanged = pyqtSignal(list)          # sorted package indexes
    modeChanged = pyqtSignal(str)
    overlayChanged = pyqtSignal()
    hint = pyqtSignal(str)                       # transient status text

    def __init__(self, session, settings, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.settings = settings
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(QRectF(-200_000, -200_000, 400_000, 400_000))
        self.scene.selectionChanged.connect(self._on_scene_selection)
        self.view = None                         # set by the view
        self.items: list[PackageItem] = []
        self.pallet = PalletItem()
        self.scene.addItem(self.pallet)
        self.geo: Geometry | None = None
        self.mode = SELECT
        self.display = {k: settings.display_option(k, d) for k, d in DISPLAY_DEFAULTS.items()}
        self.drag: Drag | None = None
        self.ghosts: list[PackageItem] = []
        self.ghost_packages: list[Package] = []   # stored-frame packages being placed
        self.ghost_snap: tuple = (None, None)
        self.add_orientation = 0
        self.order: list[int] = []               # click-order assignment so far
        self._suppress_selection = False
        self._pending_selection: list[int] | None = None
        self._last_selection: list[int] = []

        session.projectChanged.connect(self._on_project_changed)
        session.currentChanged.connect(lambda _uid: self.load())

    # ------------------------------------------------------------------ model

    def pattern(self) -> Pattern | None:
        return self.session.current_pattern()

    def load(self) -> None:
        """Show the current pattern; called when the current pattern or project changes."""
        self.cancel(silent=True)
        self._pending_selection = []         # a selection belongs to the previous pattern
        self._sync(self.pattern(), keep_view=False)

    def _on_project_changed(self, _old, _new) -> None:
        pattern = self.pattern()
        if self.geo is not None and pattern is self.geo.pattern:
            return
        if self.mode in (PLACE, ORDER):
            self.cancel(silent=True)
        self._sync(pattern, keep_view=self.geo is not None and pattern is not None
                   and self.geo.pattern.uid == pattern.uid)

    def _compute(self, pattern: Pattern) -> Geometry:
        geo = Geometry(pattern)
        dims = pattern.dims
        if not pattern.packages or not dims.is_valid():
            return geo
        try:
            box = extent(pattern.packages, dims)
            cx, cy = box.center()
            geo.cx, geo.cy = _mm(cx, dims), _mm(cy, dims)
            geo.width, geo.height = box.width(), box.height()
            for p in pattern.packages:
                w, h = _mm(p.half_width(), dims) * 2, _mm(p.half_height(), dims) * 2
                x, y = _mm(p.x, dims) - geo.cx, _mm(p.y, dims) - geo.cy
                geo.boxes.append(QRectF(x - w / 2, y - h / 2, w, h))
            geo.relative = [(p.x - cx, p.y - cy) for p in pattern.packages]
            geo.neighbours = neighbour_pairs(rects(pattern.packages, dims), dims)
        except ValueError:
            return Geometry(pattern)
        report = self.session.report(pattern.uid)
        if report is not None:
            for issue in report.issues:
                if issue.code in _GEOMETRY_ISSUES:
                    geo.invalid.update(issue.packages)
        return geo

    def _sync(self, pattern: Pattern | None, keep_view: bool) -> None:
        keep = self._pending_selection if self._pending_selection is not None else self.selected()
        self._pending_selection = None
        if pattern is None:
            self.geo = None
            self._set_items([])
            self.pallet.setVisible(False)
            self.overlayChanged.emit()
            return
        self.geo = self._compute(pattern)
        dims = pattern.dims
        if len(self.items) != len(self.geo.boxes):
            self._set_items([PackageItem(i, r.width(), r.height(), p.orientation)
                             for i, (r, p) in enumerate(zip(self.geo.boxes, pattern.packages))])
        for item, rect, pkg in zip(self.items, self.geo.boxes, pattern.packages):
            item.set_size(rect.width(), rect.height())
            item.orientation = pkg.orientation
            item.setPos(rect.center())
            item.set_state(INVALID if item.index in self.geo.invalid else NORMAL)
        self.pallet.set_size(dims.pallet_x, dims.pallet_y)
        self.pallet.setVisible(self.display["pallet"] and self.geo.valid_dims)
        self._select([i for i in keep if i < len(self.items)])
        if self.view is not None and not keep_view:
            QTimer.singleShot(0, lambda: self.fit(include_pallet=True))
        self.overlayChanged.emit()

    def _set_items(self, items: list[PackageItem]) -> None:
        self._suppress_selection = True
        for item in self.items:
            self.scene.removeItem(item)
        self.items = items
        for item in items:
            self.scene.addItem(item)
        self._suppress_selection = False

    # -------------------------------------------------------------- selection

    def selected(self) -> list[int]:
        return sorted(item.index for item in self.items if item.isSelected())

    def _select(self, indexes) -> None:
        wanted = set(indexes)
        self._suppress_selection = True
        for item in self.items:
            item.setSelected(item.index in wanted)
        self._suppress_selection = False
        self._on_scene_selection()

    def _on_scene_selection(self) -> None:
        if self._suppress_selection:
            return
        current = self.selected()
        if current != self._last_selection:
            self._last_selection = current
            self.selectionChanged.emit(current)
            self.overlayChanged.emit()

    def select_all(self) -> None:
        self._select(range(len(self.items)))

    # ------------------------------------------------------------- coordinates

    def to_stored(self, scene: QPointF) -> tuple[float, float]:
        return scene.x() + self.geo.cx, scene.y() + self.geo.cy

    def to_scene(self, x: float, y: float) -> QPointF:
        return QPointF(x - self.geo.cx, y - self.geo.cy)

    def _zoom(self) -> float:
        return self.view.transform().m11() if self.view is not None else 1.0

    # ------------------------------------------------------------ mouse input

    def item_at(self, scene_pos: QPointF) -> PackageItem | None:
        for item in self.scene.items(scene_pos):
            if isinstance(item, PackageItem) and not item.ghost:
                return item
        return None

    def press(self, scene_pos: QPointF, button, modifiers) -> bool:
        """True if the controller handled the press (otherwise: rubber band)."""
        if self.geo is None or button != Qt.MouseButton.LeftButton:
            return False
        if self.mode in (ADD, PLACE):
            self._place_ghosts(scene_pos)
            return True
        item = self.item_at(scene_pos)
        if self.mode == ORDER:
            if item is not None and item.index not in self.order:
                self.order.append(item.index)
                self.overlayChanged.emit()
                if len(self.order) == len(self.items):
                    self.finish_order()
                else:
                    self.hint.emit(f"Click order: {len(self.order)} of {len(self.items)}. "
                                   "Enter finishes, Esc restores the previous sequence.")
            return True
        if item is None:
            return False
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            item.setSelected(not item.isSelected())
            return True
        if not item.isSelected():
            self._select([item.index])
        moving = self.selected()
        self.drag = Drag(item.index, scene_pos, {i: self.items[i].pos() for i in moving})
        return True

    def move(self, scene_pos: QPointF) -> None:
        if self.mode in (ADD, PLACE):
            self._move_ghosts(scene_pos)
            return
        drag = self.drag
        if drag is None:
            return
        if not drag.active:
            if (scene_pos - drag.start).manhattanLength() * self._zoom() < DRAG_START_PX:
                return
            self._begin_drag(drag)
        delta = scene_pos - drag.start
        anchor0 = drag.origins[drag.anchor]
        sx, sy = self.to_stored(anchor0 + delta)
        radius = SNAP_PX / self._zoom()
        drag.snap_x = snapping.resolve(drag.cand_x, sx, radius) if drag.cand_x else None
        drag.snap_y = snapping.resolve(drag.cand_y, sy, radius) if drag.cand_y else None
        x = drag.snap_x.mm if drag.snap_x else sx
        y = drag.snap_y.mm if drag.snap_y else sy
        shift = self.to_scene(x, y) - anchor0
        for index, origin in drag.origins.items():
            self.items[index].setPos(origin + shift)
        texts = [c.text for c in (drag.snap_x, drag.snap_y) if c is not None]
        self.hint.emit(" · ".join(texts) if texts else "Release snaps to the nearest relation.")
        self.overlayChanged.emit()

    def _begin_drag(self, drag: Drag) -> None:
        pattern = self.geo.pattern
        refs = [(i, p) for i, p in enumerate(pattern.packages) if i not in drag.origins]
        orientation = pattern.packages[drag.anchor].orientation
        drag.cand_x = snapping.axis_candidates("x", orientation, refs, pattern.dims)
        drag.cand_y = snapping.axis_candidates("y", orientation, refs, pattern.dims)
        drag.active = True

    def release(self, scene_pos: QPointF) -> None:
        if self.mode != SELECT:
            return
        drag, self.drag = self.drag, None
        if drag is None or not drag.active:
            self.overlayChanged.emit()
            return
        if not drag.cand_x:
            # Everything is selected: a pattern has no absolute position to move to.
            self._restore(drag)
            self.hint.emit("Moving the whole pattern does not change it.")
            return
        pattern = self.geo.pattern
        anchor = pattern.packages[drag.anchor]
        sx, sy = self.to_stored(self.items[drag.anchor].pos())
        cx = snapping.resolve(drag.cand_x, sx, None)
        cy = snapping.resolve(drag.cand_y, sy, None)
        dx, dy = cx.value - anchor.x, cy.value - anchor.y
        if dx.is_zero() and dy.is_zero():
            self._restore(drag)
            return
        moved = [p.moved(dx, dy) if i in drag.origins else p for i, p in enumerate(pattern.packages)]
        self._commit("Move package" if len(drag.origins) == 1 else "Move packages", moved,
                     sorted(drag.origins))
        self.hint.emit(f"{cx.text} · {cy.text}")

    def _restore(self, drag: Drag) -> None:
        for index, origin in drag.origins.items():
            self.items[index].setPos(origin)
        self.overlayChanged.emit()

    # ---------------------------------------------------------------- commits

    def _commit(self, label: str, packages, select=None) -> None:
        pattern = self.geo.pattern
        new = normalized(packages, pattern.dims)
        self._pending_selection = list(select) if select is not None else self.selected()
        if not self.session.execute(label, lambda p: ops.set_packages(p, pattern.uid, new)):
            self._pending_selection = None
            self._sync(self.pattern(), keep_view=True)

    # ------------------------------------------------------------------ tools

    def set_mode(self, mode: str) -> None:
        if mode != self.mode:
            self.mode = mode
            self.modeChanged.emit(mode)
            self.overlayChanged.emit()

    def start_add(self) -> None:
        if self.geo is None:
            return
        self.cancel(silent=True)
        self.ghost_packages = [Package(LinearForm(), LinearForm(), self.add_orientation)]
        self._make_ghosts()
        self.set_mode(ADD)
        self.hint.emit("Add package: click to place, R rotates, Esc ends the tool.")

    def duplicate_selected(self) -> None:
        if self.geo is None or not self.selected():
            self.hint.emit("Select packages to duplicate.")
            return
        packages = self.geo.pattern.packages
        chosen = [packages[i] for i in self.selected()]
        self.cancel(silent=True)
        self.ghost_packages = chosen
        self._make_ghosts()
        self.set_mode(PLACE)
        self.hint.emit("Place the copies: click to drop, Esc cancels.")

    def _make_ghosts(self) -> None:
        dims = self.geo.pattern.dims
        for g in self.ghosts:
            self.scene.removeItem(g)
        self.ghosts = []
        for p in self.ghost_packages:
            g = PackageItem(-1, _mm(p.half_width(), dims) * 2, _mm(p.half_height(), dims) * 2,
                            p.orientation, ghost=True)
            g.setVisible(False)
            self.scene.addItem(g)
            self.ghosts.append(g)

    def _ghost_offsets(self) -> list[tuple[float, float]]:
        dims = self.geo.pattern.dims
        first = self.ghost_packages[0]
        return [(_mm(p.x - first.x, dims), _mm(p.y - first.y, dims)) for p in self.ghost_packages]

    def _move_ghosts(self, scene_pos: QPointF) -> None:
        if not self.ghosts or self.geo is None:
            return
        pattern = self.geo.pattern
        sx, sy = self.to_stored(scene_pos)
        refs = list(enumerate(pattern.packages))
        orientation = self.ghost_packages[0].orientation
        radius = SNAP_PX / self._zoom()
        cand_x = snapping.resolve(snapping.axis_candidates("x", orientation, refs, pattern.dims), sx, radius) \
            if refs else None
        cand_y = snapping.resolve(snapping.axis_candidates("y", orientation, refs, pattern.dims), sy, radius) \
            if refs else None
        self.ghost_snap = (cand_x, cand_y)
        x = cand_x.mm if cand_x else sx
        y = cand_y.mm if cand_y else sy
        for ghost, (ox, oy) in zip(self.ghosts, self._ghost_offsets()):
            ghost.setPos(self.to_scene(x + ox, y + oy))
            ghost.setVisible(True)
        texts = [c.text for c in self.ghost_snap if c is not None]
        if texts:
            self.hint.emit(" · ".join(texts))
        self.overlayChanged.emit()

    def _place_ghosts(self, scene_pos: QPointF) -> None:
        pattern = self.geo.pattern
        first = self.ghost_packages[0]
        sx, sy = self.to_stored(scene_pos)
        placed, _cx, _cy = snapping.snap_package(pattern.packages, None, first.orientation,
                                                 (sx, sy), pattern.dims)
        dx, dy = placed.x - first.x, placed.y - first.y
        new = [p.moved(dx, dy) for p in self.ghost_packages]
        count = len(pattern.packages)
        label = "Add package" if self.mode == ADD else "Duplicate packages"
        mode = self.mode
        if mode == PLACE:
            self.cancel(silent=True)
        self._commit(label, list(pattern.packages) + new, range(count, count + len(new)))
        if mode == ADD:
            self._move_ghosts(scene_pos)

    def rotate(self) -> None:
        """R: toggle the tool's orientation, or rotate the selected packages (D14)."""
        if self.mode == ADD:
            self.add_orientation = 90 if self.add_orientation == 0 else 0
            self.ghost_packages = [self.ghost_packages[0].toggled()]
            self._make_ghosts()
            if self.view is not None:
                self._move_ghosts(self.view.cursor_scene_pos())
            return
        if self.mode != SELECT or self.geo is None:
            return
        chosen = self.selected()
        if not chosen:
            self.hint.emit("Select packages to rotate.")
            return
        packages = list(self.geo.pattern.packages)
        dims = self.geo.pattern.dims
        for i in chosen:
            p = packages[i]
            centre = (_mm(p.x, dims), _mm(p.y, dims))
            packages[i], _, _ = snapping.snap_package(packages, i, p.toggled().orientation, centre, dims)
        self._commit("Rotate package" if len(chosen) == 1 else "Rotate packages", packages, chosen)

    def delete_selected(self) -> None:
        chosen = set(self.selected())
        if self.geo is None or not chosen or self.mode != SELECT:
            return
        remaining = [p for i, p in enumerate(self.geo.pattern.packages) if i not in chosen]
        self._commit("Delete packages" if len(chosen) > 1 else "Delete package", remaining, [])

    # --------------------------------------------------------------- sequence

    def auto_order(self) -> None:
        if self.geo is None or not self.geo.valid_dims:
            return
        pattern = self.geo.pattern
        ordered = auto_order(pattern.packages, pattern.dims)
        if ordered == pattern.packages:
            self.hint.emit("The sequence already follows the automatic order.")
            return
        self._commit("Automatic sequence", ordered, [])

    def move_in_sequence(self, source: int, target: int) -> None:
        if self.geo is None:
            return
        order = list(range(len(self.geo.pattern.packages)))
        order.insert(target, order.pop(source))
        self._commit("Change sequence", reordered(self.geo.pattern.packages, order), [target])

    def start_order(self) -> None:
        if self.geo is None or not self.items:
            return
        self.cancel(silent=True)
        self.order = []
        self.set_mode(ORDER)
        self.hint.emit("Click the packages in the new placement order. Esc restores the previous sequence.")

    def finish_order(self) -> None:
        if self.mode != ORDER:
            return
        n = len(self.items)
        rest = [i for i in range(n) if i not in self.order]
        new_order = self.order + rest
        self.order = []
        self.set_mode(SELECT)
        if new_order != list(range(n)):
            self._commit("Click order", reordered(self.geo.pattern.packages, new_order), [])

    # ------------------------------------------------------------------ misc

    def cancel(self, silent: bool = False) -> None:
        """Esc: end the active tool or temporary operation without changing the project."""
        if self.drag is not None and self.drag.active:
            self._restore(self.drag)
        self.drag = None
        for g in self.ghosts:
            self.scene.removeItem(g)
        self.ghosts, self.ghost_packages, self.ghost_snap = [], [], (None, None)
        if self.mode == ORDER and not silent:
            self.hint.emit("Click order cancelled; the previous sequence is kept.")
        self.order = []
        if self.mode != SELECT:
            self.set_mode(SELECT)
        elif not silent and self.selected():
            self._select([])
        self.overlayChanged.emit()

    def set_display(self, name: str, value: bool) -> None:
        self.display[name] = value
        self.settings.set_display_option(name, value)
        if name == "pallet":
            self.pallet.setVisible(value and self.geo is not None and self.geo.valid_dims)
        self.overlayChanged.emit()

    def fit(self, include_pallet: bool = False) -> None:
        if self.view is None or self.geo is None or not self.geo.boxes:
            return
        rect = QRectF()
        for box in self.geo.boxes:
            rect = rect.united(box)
        if include_pallet and self.geo.valid_dims:
            rect = rect.united(self.pallet.rect())
        self.view.fit_rect(rect)
