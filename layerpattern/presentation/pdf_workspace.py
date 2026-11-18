"""PDF workspace: import PDFs, page thumbnails, page view with region selection,
background recognition, proposal review and explicit acceptance.

Proposals are temporary: they become project data only through Accept (one undoable
command). Rendering and recognition run in the TaskRunner; the GUI thread only turns
finished QImages into pixmaps and paints overlays.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap, QTransform
from PyQt6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFormLayout, QFrame, QGraphicsPixmapItem, QGraphicsScene,
    QGraphicsView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QSplitter,
    QVBoxLayout, QWidget
)
from qt_controls_pyrs import (
    CompactButton, CompactDropdown, CompactGroupBox, CompactIntField, HaloScrollBar, flash_taskbar
)

from layerpattern.domain import operations as ops
from layerpattern.domain.model import Dimensions, Origin, Pattern, SourceRef
from layerpattern.presentation import icons
from layerpattern.presentation.preview import pattern_image
from layerpattern.presentation.theme import ACCENT, ERROR, OK, WARNING, editor_colors

LEVEL_COLOR = {"ok": OK, "warning": WARNING, "error": ERROR}
LEVEL_TEXT = {"ok": "", "warning": "uncertain", "error": "incomplete"}
THUMB_PX = 150
PAGE_PX = 2400


def to_qimage(pixels) -> QImage:
    """RGB numpy array -> independent QImage (safe to create in a worker thread)."""
    import numpy as np

    data = np.ascontiguousarray(pixels)
    h, w = data.shape[:2]
    return QImage(data.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def overlap(a, b) -> float:
    """Intersection over the smaller area of two page rectangles."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return w * h / smaller if smaller > 0 else 0.0


class Entry:
    """One unaccepted proposal."""

    _next = 1

    def __init__(self, pdf_id: int, proposal) -> None:
        self.key = Entry._next
        Entry._next += 1
        self.pdf_id = pdf_id
        self.proposal = proposal
        self.checked = proposal.level != "error"     # red ones need a conscious choice


class PageView(QGraphicsView):
    """One page in PDF points (Y down); proposals and sources are painted on top."""

    regionSelected = pyqtSignal(tuple)
    proposalClicked = pyqtSignal(int)

    def __init__(self, workspace: "PdfWorkspace") -> None:
        super().__init__()
        self.ws = workspace
        self.setScene(QGraphicsScene(self))
        self.pixmap = QGraphicsPixmapItem()
        self.pixmap.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene().addItem(self.pixmap)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.region_mode = False
        self.page_size = (595.0, 842.0)
        self.source_rect = None
        self._drag_start: QPointF | None = None
        self._drag_now: QPointF | None = None
        self._pan: QPointF | None = None

    def set_page(self, image: QImage | None, size: tuple[float, float], scale: float) -> None:
        self.page_size = size
        if image is None:
            self.pixmap.setPixmap(QPixmap())
        else:
            self.pixmap.setPixmap(QPixmap.fromImage(image))
            self.pixmap.setTransform(QTransform.fromScale(1 / scale, 1 / scale))
        self.scene().setSceneRect(QRectF(-2000, -2000, size[0] + 4000, size[1] + 4000))
        self.viewport().update()

    def fit(self, rect: QRectF | None = None) -> None:
        rect = rect or QRectF(0, 0, *self.page_size)
        margin = 24.0
        z = min((self.viewport().width() - 2 * margin) / max(rect.width(), 1),
                (self.viewport().height() - 2 * margin) / max(rect.height(), 1))
        self.setTransform(QTransform.fromScale(z, z))
        self.centerOn(rect.center())

    def wheelEvent(self, event) -> None:
        factor = 1.0015 ** event.angleDelta().y()
        anchor = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        moved = self.mapToScene(event.position().toPoint())
        self.translate(moved.x() - anchor.x(), moved.y() - anchor.y())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan = event.position()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self.mapToScene(event.position().toPoint())
            if self.region_mode:
                self._drag_start = self._drag_now = pos
                return
            key = self.ws.proposal_at(pos)
            if key is not None:
                self.proposalClicked.emit(key)

    def mouseMoveEvent(self, event) -> None:
        if self._pan is not None:
            delta = event.position() - self._pan
            self._pan = event.position()
            z = self.transform().m11()
            self.translate(delta.x() / z, delta.y() / z)
            return
        if self._drag_start is not None:
            self._drag_now = self.mapToScene(event.position().toPoint())
            self.viewport().update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan = None
            return
        if self._drag_start is not None:
            rect = QRectF(self._drag_start, self._drag_now).normalized()
            self._drag_start = self._drag_now = None
            self.viewport().update()
            if rect.width() > 8 and rect.height() > 8:
                self.regionSelected.emit((rect.left(), rect.top(), rect.right(), rect.bottom()))

    def cancel_drag(self) -> None:
        self._drag_start = self._drag_now = None
        self.viewport().update()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, editor_colors().background)
        painter.fillRect(QRectF(0, 0, *self.page_size), QColor("white"))

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        mapping = self.viewportTransform()
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        def screen(r) -> QRectF:
            return mapping.mapRect(QRectF(QPointF(r[0], r[1]), QPointF(r[2], r[3])))

        for entry in self.ws.page_entries():
            p = entry.proposal
            color = QColor(LEVEL_COLOR[p.level])
            selected = entry.key == self.ws.selected_key
            fill = QColor(color)
            fill.setAlpha(60 if selected else 28)
            uncertain = set(p.reconstruction.uncertain) | set(p.reconstruction.estimated)
            for index, r in enumerate(p.rects):
                box = screen(r)
                painter.setBrush(fill)
                style = Qt.PenStyle.DashLine if index in uncertain else Qt.PenStyle.SolidLine
                painter.setPen(QPen(QColor(WARNING) if index in uncertain else color,
                                    2.0 if selected else 1.2, style))
                painter.drawRect(box)
                if selected and min(box.width(), box.height()) > 16:
                    painter.setPen(QColor("black"))
                    painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), str(index + 1))
            region = screen(p.region)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(color, 1.0, Qt.PenStyle.DotLine))
            painter.drawRect(region)
        if self.source_rect is not None:
            painter.setPen(QPen(QColor(ACCENT), 2.5, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(screen(self.source_rect).adjusted(-4, -4, 4, 4))
        if self._drag_start is not None and self._drag_now is not None:
            box = mapping.mapRect(QRectF(self._drag_start, self._drag_now).normalized())
            painter.setPen(QPen(QColor(ACCENT), 1.5, Qt.PenStyle.DashLine))
            tint = QColor(ACCENT)
            tint.setAlpha(30)
            painter.setBrush(tint)
            painter.drawRect(box)
        painter.restore()


class PdfWorkspace(QWidget):
    def __init__(self, session, settings, runner, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.settings = settings
        self.runner = runner
        self.pdf_id: int | None = None
        self.page = 0
        self.page_count = 0
        self.entries: list[Entry] = []
        self.selected_key: int | None = None
        self._thumbs: dict[tuple[str, int], QImage] = {}
        self._pages: dict[tuple[str, int], tuple[QImage, tuple, float]] = {}

        self._build_actions()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left())
        self.view = PageView(self)
        self.view.regionSelected.connect(self.recognize_region)
        self.view.proposalClicked.connect(self.select_entry)
        splitter.addWidget(self.view)
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([210, 900, 330])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        for action in (self.act_cancel, self.act_fit_page):
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.addAction(action)

        session.projectChanged.connect(lambda *_: self.refresh_pdfs())
        self.refresh_pdfs()
        self._update_actions()

    # ------------------------------------------------------------- building

    def _action(self, text, icon, slot, tip="", checkable=False, shortcut=None) -> QAction:
        action = QAction(icons.icon(icon), text, self)
        action.setStatusTip(tip)
        action.setCheckable(checkable)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        return action

    def _build_actions(self) -> None:
        self.act_import = self._action("Import PDF", "pdf_import", self.import_pdf, "Add PDF files to the project")
        self.act_relink = self._action("Relink", "relink", self.relink, "Point a missing PDF to its new location")
        self.act_recognize = self._action("Recognize", "recognize_page", self.recognize_pages,
                                          "Recognize patterns on the selected pages")
        self.act_region = self._action("Region", "recognize_region", self._toggle_region,
                                       "Draw a rectangle; only that area is recognized", True)
        self.act_cancel = self._action("Cancel", "cancel", self.escape, "Stop recognition / leave region tool",
                                       shortcut="Esc")
        self.act_accept = self._action("Accept", "accept", self.accept_checked, "Add the checked proposals as patterns")
        self.act_accept_all = self._action("Accept All Valid", "accept_all", self.accept_valid,
                                           "Add every proposal without a red warning")
        self.act_discard = self._action("Discard", "delete", self.discard_checked, "Drop the checked proposals")
        self.act_fit_page = self._action("Fit Page", "fit", lambda: self.view.fit(), shortcut="F")

    def _build_left(self) -> QWidget:
        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(4, 6, 4, 4)
        self.pdf_choice = CompactDropdown()
        self.pdf_choice.setPlaceholderText("No PDF imported")
        self.pdf_choice.currentIndexChanged.connect(self._on_pdf_chosen)
        column.addWidget(self.pdf_choice)
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumbs.setIconSize(QSize(THUMB_PX, THUMB_PX))
        self.thumbs.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumbs.setMovement(QListWidget.Movement.Static)
        self.thumbs.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.thumbs.setVerticalScrollBar(HaloScrollBar(self.thumbs))
        self.thumbs.currentRowChanged.connect(self._on_page_chosen)
        column.addWidget(self.thumbs, 1)
        return box

    def _build_right(self) -> QWidget:
        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(6, 6, 6, 6)
        self.caption = QLabel("Proposals")
        bold = self.caption.font()
        bold.setBold(True)
        self.caption.setFont(bold)
        column.addWidget(self.caption)
        self.list = QListWidget()
        self.list.setIconSize(QSize(56, 56))
        self.list.setVerticalScrollBar(HaloScrollBar(self.list))
        self.list.currentItemChanged.connect(
            lambda item, _prev: item is not None and self.select_entry(item.data(Qt.ItemDataRole.UserRole)))
        self.list.itemChanged.connect(self._on_item_changed)
        column.addWidget(self.list, 1)
        self.details = QLabel()
        self.details.setWordWrap(True)
        column.addWidget(self.details)

        self.compare = QFrame()
        compare = QVBoxLayout(self.compare)
        compare.setContentsMargins(0, 0, 0, 0)
        self.compare_text = QLabel()
        self.compare_text.setWordWrap(True)
        pictures = QHBoxLayout()
        self.compare_old, self.compare_new = QLabel(), QLabel()
        pictures.addWidget(self.compare_old)
        pictures.addWidget(self.compare_new)
        self.replace_button = CompactButton("Replace pattern")
        self.replace_button.clicked.connect(self.replace_selected)
        compare.addWidget(self.compare_text)
        compare.addLayout(pictures)
        compare.addWidget(self.replace_button)
        self.compare.hide()
        column.addWidget(self.compare)

        group = CompactGroupBox("Example values for accepted patterns")
        form = QFormLayout(group)
        dims = self.settings.default_dimensions
        self.dims_fields = {}
        for key, text, minimum in (("kl", "KL", 1), ("kb", "KB", 1), ("d", "D", 0),
                                   ("pallet_x", "Pallet width", 1), ("pallet_y", "Pallet length", 1)):
            field = CompactIntField("mm", minimum=minimum, maximum=99_999, value=getattr(dims, key))
            form.addRow(text, field)
            self.dims_fields[key] = field
        self.fit_button = CompactButton("Fit to pallet")
        self.fit_button.setToolTip("Fill KL and KB with round values that fit the selected proposal\n"
                                   "onto the pallet above (D and pallet stay as entered).")
        self.fit_button.clicked.connect(self.fit_selected)
        form.addRow("", self.fit_button)
        column.addWidget(group)
        return box

    def fit_selected(self) -> None:
        from layerpattern.domain.fitting import fit_to_pallet

        entry = self._entry(self.selected_key)
        if entry is None:
            self.session.notify("Select a proposal first; its KL and KB are fitted to the pallet.",
                                "warning")
            return
        dims = self.accept_dims()
        rec = entry.proposal.reconstruction
        results = fit_to_pallet(rec.packages, rec.hints, dims.pallet_x, dims.pallet_y, dims.d,
                                self.settings.fit_step, self.settings.fit_band)
        if not results:
            self.session.notify("No KL/KB found that keeps this proposal valid on the pallet.", "warning")
            return
        best = results[0]
        self.dims_fields["kl"].set_value(best.kl)
        self.dims_fields["kb"].set_value(best.kb)
        self._refresh_list()
        self._show_details(entry)
        note = "" if best.drawing_kept else " The proportions of the drawing could not be kept."
        self.session.notify("Fit to pallet: " + best.summary() + "." + note
                            + " Accept to use these values.", "info" if best.drawing_kept else "warning")

    # ------------------------------------------------------------- PDFs

    def current_path(self) -> str | None:
        project = self.session.project
        ref = project.pdf(self.pdf_id) if project is not None and self.pdf_id is not None else None
        return ref.path if ref is not None else None

    def refresh_pdfs(self) -> None:
        project = self.session.project
        refs = list(project.pdfs) if project else []
        self.pdf_choice.blockSignals(True)
        self.pdf_choice.clear()
        for ref in refs:
            missing = "" if os.path.exists(ref.path) else "  (missing)"
            self.pdf_choice.addItem(os.path.basename(ref.path) + missing, ref.pdf_id)
        ids = [ref.pdf_id for ref in refs]
        if self.pdf_id not in ids:
            self.pdf_id = ids[-1] if ids else None
            self._load_pdf()
        self.pdf_choice.setCurrentIndex(ids.index(self.pdf_id) if self.pdf_id in ids else -1)
        self.pdf_choice.blockSignals(False)
        self._update_actions()

    def _on_pdf_chosen(self, index: int) -> None:
        pdf_id = self.pdf_choice.itemData(index) if index >= 0 else None
        if pdf_id != self.pdf_id:
            self.pdf_id = pdf_id
            self._load_pdf()

    def _load_pdf(self) -> None:
        """Thumbnails in the background, page by page."""
        self.runner.invalidate("thumbnails")
        self.runner.invalidate("page")
        self.thumbs.clear()
        self.page_count = 0
        self.view.set_page(None, (595.0, 842.0), 1.0)
        path = self.current_path()
        if path is None:
            return
        if not os.path.exists(path):
            self.session.notify(f"PDF not found: {path}. Patterns stay editable; use Relink to "
                                "restore the source view.", "warning")
            return
        seen_before = any(key[0] == path for key in self._thumbs)

        def job(cancel, progress):
            from layerpattern.infrastructure.pdf_source import PdfFile
            with PdfFile(path) as pdf:
                count = pdf.page_count()
                progress(("count", count))
                for i in range(count):
                    if cancel():
                        return None
                    if (path, i) not in self._thumbs:
                        progress(("thumb", i, to_qimage(pdf.thumbnail(i, THUMB_PX * 2).pixels)))
            return count

        def on_progress(payload):
            if payload[0] == "count":
                self.page_count = payload[1]
                placeholder = QIcon(icons.tinted("pdf_import", "#888888", THUMB_PX))
                for i in range(payload[1]):
                    item = QListWidgetItem(placeholder, f"Page {i + 1}")
                    image = self._thumbs.get((path, i))
                    if image is not None:
                        item.setIcon(QIcon(QPixmap.fromImage(image)))
                    self.thumbs.addItem(item)
                if payload[1]:
                    self.thumbs.setCurrentRow(min(self.page, payload[1] - 1) if seen_before else 0)
            else:
                _kind, i, image = payload
                self._thumbs[(path, i)] = image
                if i < self.thumbs.count():
                    self.thumbs.item(i).setIcon(QIcon(QPixmap.fromImage(image)))

        self.runner.start("thumbnails", job, lambda _n: None, self._task_failed, on_progress)

    def _on_page_chosen(self, row: int) -> None:
        if row < 0:
            return
        self.page = row
        self._render_page()
        self.view.viewport().update()

    def _render_page(self, then=None) -> None:
        path = self.current_path()
        if path is None:
            return
        key = (path, self.page)
        if key in self._pages:
            image, size, scale = self._pages[key]
            self.view.set_page(image, size, scale)
            self.view.fit()
            if then:
                then()
            return
        page = self.page

        def job(_cancel, _progress):
            from layerpattern.infrastructure.pdf_source import PdfFile
            with PdfFile(path) as pdf:
                size = pdf.page_size(page)
                scale = PAGE_PX / max(size)
                return to_qimage(pdf.render(page, scale).pixels), size, scale

        def done(result):
            image, size, scale = result
            self._pages[key] = result
            if len(self._pages) > 12:
                self._pages.pop(next(iter(self._pages)))
            self.view.set_page(image, size, scale)
            self.view.fit()
            if then:
                then()

        self.runner.start("page", job, done, self._task_failed)

    def import_pdf(self) -> None:
        if not self.session.has_project():
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Import PDF", self.settings.last_dir("pdf"),
                                                "PDF (*.pdf)")
        if not paths:
            return
        self.settings.set_last_dir("pdf", os.path.dirname(paths[0]))

        def edit(project):
            pdf_id = None
            for path in paths:
                project, pdf_id = ops.add_pdf(project, os.path.normpath(path))
            return project

        if self.session.execute("Import PDF", edit):
            project = self.session.project
            self.pdf_id = next(r.pdf_id for r in project.pdfs if r.path == os.path.normpath(paths[-1]))
            self.refresh_pdfs()
            self._load_pdf()
            self.session.notify(f"Imported {len(paths)} PDF file(s). Select pages and press Recognize.")

    def relink(self) -> None:
        if self.pdf_id is None:
            return
        old = self.current_path() or ""
        path, _ = QFileDialog.getOpenFileName(self, f"Relink {os.path.basename(old)}",
                                              os.path.dirname(old), "PDF (*.pdf)")
        if path:
            pdf_id = self.pdf_id
            self.session.execute("Relink PDF", lambda p: ops.relink_pdf(p, pdf_id, os.path.normpath(path)))
            self._load_pdf()

    # ------------------------------------------------------------- recognition

    def accept_dims(self) -> Dimensions:
        return Dimensions(**{k: f.value() for k, f in self.dims_fields.items()})

    def _start_recognition(self, pages: list[int], region) -> None:
        path = self.current_path()
        if path is None or not os.path.exists(path):
            self.session.notify("Select an available PDF first.", "warning")
            return
        dims = self.accept_dims()
        if not dims.is_valid():
            self.session.notify(" ".join(dims.problems()), "warning")
            return
        sensitivity, max_packages, pdf_id = self.settings.sensitivity, self.settings.max_packages, self.pdf_id

        def job(cancel, progress):
            from layerpattern.domain.cancel import Cancelled
            from layerpattern.infrastructure.recognition.pipeline import recognize
            total = 0
            for done, page in enumerate(pages, start=1):
                if cancel():
                    raise Cancelled()
                found = recognize(path, page, region, sensitivity, dims, cancel, max_packages)
                total += len(found)
                progress((done, len(pages), page, found))
            return total

        def on_progress(payload):
            done, count, page, found = payload
            # A new result for a page (or region) replaces earlier unaccepted proposals there.
            self.entries = [e for e in self.entries if not (
                e.pdf_id == pdf_id and e.proposal.page == page
                and (region is None or overlap(e.proposal.region, region) > 0.5))]
            self.entries += [Entry(pdf_id, p) for p in found]
            self._refresh_list()
            self.session.notify(f"Recognizing: page {done} of {count} done...")

        def on_done(total):
            self._set_busy(False)
            self.session.notify(f"Recognition finished: {total} proposal(s). Review and accept them.")
            window = self.window()
            if not window.isActiveWindow():
                flash_taskbar(int(window.winId()))

        def on_cancel():
            self._set_busy(False)
            self.session.notify("Recognition cancelled. The project is unchanged.")

        self._set_busy(True)
        self.runner.start("recognition", job, on_done, self._task_failed, on_progress, on_cancel)

    def recognize_pages(self) -> None:
        pages = sorted(self.thumbs.row(item) for item in self.thumbs.selectedItems()) or [self.page]
        self._start_recognition(pages, None)

    def recognize_region(self, region) -> None:
        self._start_recognition([self.page], region)

    def _toggle_region(self) -> None:
        self.view.region_mode = self.act_region.isChecked()
        self.view.setCursor(Qt.CursorShape.CrossCursor if self.view.region_mode else Qt.CursorShape.ArrowCursor)
        if self.view.region_mode:
            self.session.notify("Draw a rectangle around one pattern; Esc leaves the region tool.")

    def escape(self) -> None:
        if self.runner.busy("recognition"):
            self.runner.cancel("recognition")
            self._set_busy(False)
            self.session.notify("Recognition cancelled. The project is unchanged.")
        elif self.act_region.isChecked():
            self.act_region.setChecked(False)
            self._toggle_region()
            self.view.cancel_drag()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._update_actions()

    def _task_failed(self, message: str, details: str) -> None:
        self._set_busy(False)
        self.session.notify(f"Background task failed: {message}", "error", details)

    # ------------------------------------------------------------- proposals

    def page_entries(self) -> list[Entry]:
        return [e for e in self.entries if e.pdf_id == self.pdf_id and e.proposal.page == self.page]

    def proposal_at(self, pos: QPointF) -> int | None:
        for entry in self.page_entries():
            x0, y0, x1, y1 = entry.proposal.region
            if x0 <= pos.x() <= x1 and y0 <= pos.y() <= y1:
                return entry.key
        return None

    def _entry(self, key) -> Entry | None:
        return next((e for e in self.entries if e.key == key), None)

    def _preview(self, packages, size=56) -> QPixmap:
        pattern = Pattern(0, 0, packages, self.accept_dims() if self.accept_dims().is_valid() else Dimensions())
        return QPixmap.fromImage(pattern_image(pattern, size, self.devicePixelRatioF()))

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        entry = self._entry(item.data(Qt.ItemDataRole.UserRole))
        if entry is not None:
            entry.checked = item.checkState() == Qt.CheckState.Checked
        self._update_actions()

    def _refresh_list(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for entry in self.entries:
            p = entry.proposal
            note = LEVEL_TEXT[p.level]
            name = os.path.basename(self.session.project.pdf(entry.pdf_id).path) \
                if self.session.project and self.session.project.pdf(entry.pdf_id) else "?"
            item = QListWidgetItem(QIcon(self._preview(p.reconstruction.packages)),
                                   f"Page {p.page + 1} · {len(p.rects)} packages"
                                   + (f"  [{note}]" if note else "") + f"\n{name}")
            item.setData(Qt.ItemDataRole.UserRole, entry.key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if entry.checked else Qt.CheckState.Unchecked)
            item.setForeground(QColor(LEVEL_COLOR[p.level]) if p.level != "ok" else self.palette().text().color())
            item.setToolTip("\n".join(p.messages) or "No warnings.")
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.caption.setText(f"Proposals ({len(self.entries)})")
        if self.selected_key not in {e.key for e in self.entries}:
            self.selected_key = None
            self._show_details(None)
        self._update_actions()
        self.view.viewport().update()

    def select_entry(self, key) -> None:
        entry = self._entry(key)
        if entry is None:
            return
        self.selected_key = key
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.ItemDataRole.UserRole) == key:
                self.list.blockSignals(True)
                self.list.setCurrentRow(row)
                self.list.blockSignals(False)
        if entry.pdf_id != self.pdf_id:
            self.pdf_id = entry.pdf_id
            self.refresh_pdfs()
            self._load_pdf()
        if entry.proposal.page != self.page and entry.proposal.page < self.thumbs.count():
            self.thumbs.setCurrentRow(entry.proposal.page)
        self._show_details(entry)
        self.view.viewport().update()

    def _existing_for(self, entry: Entry) -> Pattern | None:
        """A pattern already accepted from (roughly) the same place: re-recognition (D17)."""
        project = self.session.project
        if project is None:
            return None
        for pattern in project.patterns:
            src = pattern.source
            if src and src.pdf_id == entry.pdf_id and src.page == entry.proposal.page \
                    and overlap(src.rect, entry.proposal.region) > 0.5:
                return pattern
        return None

    def _show_details(self, entry: Entry | None) -> None:
        if entry is None:
            self.details.setText("")
            self.compare.hide()
            return
        p = entry.proposal
        color = LEVEL_COLOR[p.level]
        lines = [f"<span style='color:{color}'>&#9632;</span> " + m for m in p.messages] or ["No warnings."]
        if p.reconstruction.hints:
            from layerpattern.domain.geometry import Condition
            lines.append("Drawing proportions: " + "; ".join(
                Condition(h).text(ge="=") for h in p.reconstruction.hints))
        self.details.setText("<br>".join(lines))
        existing = self._existing_for(entry)
        if existing is None:
            self.compare.hide()
            return
        self.compare_text.setText(f"This area was accepted before as <b>pattern {existing.pattern_id}</b> "
                                  "(left). Accept adds a new pattern; Replace overwrites its geometry "
                                  "(undoable). Manual edits are never replaced automatically.")
        self.compare_old.setPixmap(QPixmap.fromImage(pattern_image(existing, 110, self.devicePixelRatioF())))
        self.compare_new.setPixmap(self._preview(p.reconstruction.packages, 110))
        self.replace_button.setText(f"Replace pattern {existing.pattern_id}")
        self.compare.show()

    def _checked(self) -> list[Entry]:
        return [e for e in self.entries if e.checked]

    def accept_checked(self) -> None:
        self._accept(self._checked())

    def accept_valid(self) -> None:
        self._accept([e for e in self.entries if e.proposal.level != "error"])

    def _accept(self, chosen: list[Entry]) -> None:
        if not chosen or not self.session.has_project():
            return
        dims = self.accept_dims()
        if not dims.is_valid():
            self.session.notify(" ".join(dims.problems()), "warning")
            return

        def edit(project):
            first = None
            for e in chosen:
                source = SourceRef(e.pdf_id, e.proposal.page, tuple(e.proposal.region))
                rec = e.proposal.reconstruction
                project, uid = ops.add_pattern(project, rec.packages, dims, source=source,
                                               origin=Origin.RECOGNIZED, hints=rec.hints)
                first = first or uid
            return project, first

        before = {p.uid for p in self.session.project.patterns}
        label = f"Accept {len(chosen)} proposal" + ("s" if len(chosen) > 1 else "")
        if self.session.execute(label, edit):
            ids = sorted(p.pattern_id for p in self.session.project.patterns if p.uid not in before)
            done = {e.key for e in chosen}
            self.entries = [e for e in self.entries if e.key not in done]
            self._refresh_list()
            self.session.notify(f"Accepted as pattern {', '.join(map(str, ids))}. Check and verify "
                                "them in the editor.")

    def replace_selected(self) -> None:
        entry = self._entry(self.selected_key)
        existing = self._existing_for(entry) if entry else None
        if entry is None or existing is None:
            return
        source = SourceRef(entry.pdf_id, entry.proposal.page, tuple(entry.proposal.region))
        if self.session.execute(f"Replace pattern {existing.pattern_id}",
                                lambda p: ops.replace_geometry(p, existing.uid, entry.proposal.reconstruction.packages,
                                                               source, entry.proposal.reconstruction.hints)):
            self.entries = [e for e in self.entries if e.key != entry.key]
            self._refresh_list()

    def discard_checked(self) -> None:
        drop = {e.key for e in self._checked()}
        self.entries = [e for e in self.entries if e.key not in drop]
        self._refresh_list()

    def confirm_discard_proposals(self) -> bool:
        if not self.entries:
            return True
        answer = QMessageBox.question(
            self, "Unaccepted proposals",
            f"{len(self.entries)} recognition proposal(s) have not been accepted and will be lost.",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        return answer == QMessageBox.StandardButton.Discard

    def project_replaced(self) -> None:
        self.runner.invalidate("recognition")
        self.runner.invalidate("thumbnails")
        self.entries = []
        self.pdf_id = None
        self._set_busy(False)
        self.refresh_pdfs()
        self._refresh_list()

    # ------------------------------------------------------------- source view

    def show_source(self, pattern: Pattern) -> bool:
        src = pattern.source
        project = self.session.project
        if src is None or project is None or project.pdf(src.pdf_id) is None:
            self.session.notify(f"Pattern {pattern.pattern_id} has no PDF source.", "warning")
            return False
        path = project.pdf(src.pdf_id).path
        if not os.path.exists(path):
            self.session.notify(f"PDF not found: {path}. Use Relink in the PDF tab.", "warning")
            self.pdf_id = src.pdf_id
            self.refresh_pdfs()
            return False
        if src.pdf_id != self.pdf_id:
            self.pdf_id = src.pdf_id
            self.refresh_pdfs()
            self._load_pdf()
        self.page = src.page
        self.view.source_rect = src.rect

        def zoom():
            x0, y0, x1, y1 = src.rect
            self.view.fit(QRectF(x0, y0, x1 - x0, y1 - y0).adjusted(-40, -40, 40, 40))

        if src.page < self.thumbs.count():
            self.thumbs.blockSignals(True)
            self.thumbs.setCurrentRow(src.page)
            self.thumbs.blockSignals(False)
        self._render_page(then=zoom)
        return True

    # ------------------------------------------------------------- state

    def _update_actions(self) -> None:
        busy = getattr(self, "_busy", False)
        has_project = self.session.has_project()
        available = self.current_path() is not None and os.path.exists(self.current_path() or "")
        self.act_import.setEnabled(has_project)
        self.act_relink.setEnabled(self.pdf_id is not None)
        self.act_recognize.setEnabled(available and not busy)
        self.act_region.setEnabled(available and not busy)
        self.act_cancel.setEnabled(busy or self.act_region.isChecked())
        checked = bool(self._checked())
        self.act_accept.setEnabled(checked and not busy)
        self.act_accept_all.setEnabled(any(e.proposal.level != "error" for e in self.entries) and not busy)
        self.act_discard.setEnabled(checked)

    def ribbon_groups(self):
        return (("PDF", ((self.act_import, "large"), (self.act_relink, "small"), (self.act_fit_page, "small"))),
                ("Recognize", ((self.act_recognize, "large"), (self.act_region, "large"), (self.act_cancel, "small"))),
                ("Proposals", ((self.act_accept, "large"), (self.act_accept_all, "small"),
                               (self.act_discard, "small"))))

