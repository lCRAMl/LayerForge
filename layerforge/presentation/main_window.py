"""Main window: command bar, tabs (Start, Editor, PDF, Help), floating status line.

Button handlers only route to the session, the editor controller or a dialog; all
decisions about patterns live in the domain functions they call.
"""

from __future__ import annotations

import traceback
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog, QMainWindow, QMenu, QSizePolicy, QSplitter, QVBoxLayout, QWidget
)
from qt_controls_pyrs import HaloCommandBar, HaloTabWidget, StatusBar

from layerforge import APP_NAME
from layerforge.domain import operations as ops
from layerforge.domain.export_model import is_verified
from layerforge.domain.model import Origin, Project
from layerforge.infrastructure import project_store
from layerforge.presentation import dialogs, icons
from layerforge.presentation.editor.controller import ADD, EditorController
from layerforge.presentation.editor.view import EditorView
from layerforge.presentation.help_tab import HelpTab
from layerforge.presentation.pattern_list import PatternList
from layerforge.presentation.properties import PropertiesPanel
from layerforge.presentation.session import ProjectSession
from layerforge.presentation.start_page import StartPage
from layerforge.presentation.theme import dark_title_bar

PROJECT_FILTER = ("LayerForge project (*" + " *".join((project_store.EXTENSION,
                  *project_store.LEGACY_EXTENSIONS)) + ")")


class AppTabs(HaloTabWidget):
    """Shorter, sharper slide than the library default: tabs are switched often here."""

    SLIDE_MS = 190
    BLUR = 3


class MainWindow(QMainWindow):
    def __init__(self, settings) -> None:
        super().__init__()
        self.settings = settings
        self.session = ProjectSession(settings, self)
        self.ctrl = EditorController(self.session, settings, self)
        from layerforge.presentation.pdf_workspace import PdfWorkspace
        from layerforge.presentation.workers import TaskRunner
        self.runner = TaskRunner(self)
        self.pdf_workspace = PdfWorkspace(self.session, settings, self.runner)
        self.setWindowIcon(icons.app_icon())
        self.resize(1440, 900)

        central = QWidget()
        self.setCentralWidget(central)
        column = QVBoxLayout(central)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        self._build_actions()
        self.bar = HaloCommandBar()
        self._build_bar()
        column.addWidget(self.bar)

        self.tabs = AppTabs()
        self.start = StartPage(settings)
        self.start.newRequested.connect(self.new_project)
        self.start.openRequested.connect(self.open_project)
        self.start.importRequested.connect(self.import_db)
        self.start.recentRequested.connect(self.open_path)
        self.tabs.addTab(self.start, "Start")
        self.tabs.addTab(self._build_editor_page(), "Editor")
        self.pdf_page = self.pdf_workspace
        self.tabs.addTab(self.pdf_page, "PDF")
        self.help = HelpTab()
        self.tabs.addTab(self.help, "Help")
        self.tabs.currentChanged.connect(self._on_tab)
        column.addWidget(self.tabs, 1)

        slot = QWidget()
        slot.setFixedHeight(24)
        slot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        column.addWidget(slot)
        self.status = StatusBar(slot, self)
        self.status.details_requested.connect(lambda msg, det: dialogs.show_details(self, msg, det))
        self.session.message.connect(self.status.show_message)
        self.ctrl.hint.connect(self.status.setText)

        self.session.stateChanged.connect(self._update_state)
        self.session.projectChanged.connect(lambda *_: self._update_state())
        self.session.currentChanged.connect(lambda *_: self._update_state())
        self.ctrl.selectionChanged.connect(lambda *_: self._update_state())
        self.ctrl.modeChanged.connect(self._on_mode)

        geometry = settings.window_geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)
        self._update_state()
        self._on_tab(0)
        self.status.setText("Ready.")

    # ------------------------------------------------------------- actions

    def _action(self, name: str, text: str, icon: str, slot, shortcut=None, tip: str = "",
                checkable: bool = False) -> QAction:
        action = QAction(icons.icon(icon), text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if tip:
            action.setStatusTip(tip)
        action.setCheckable(checkable)
        action.triggered.connect(slot)
        setattr(self, f"act_{name}", action)
        return action

    def _build_actions(self) -> None:
        a = self._action
        # Window-wide commands.
        window = [
            a("new", "New", "new", self.new_project, "Ctrl+N", "Create a new project"),
            a("open", "Open", "open", self.open_project, "Ctrl+O", "Open a project file"),
            a("save", "Save", "save", self.save, "Ctrl+S", "Save the project"),
            a("save_as", "Save As...", "save_as", self.save_as, "Ctrl+Shift+S"),
            a("import_db", "Import DB...", "import_db", self.import_db,
              tip="Start a new project from a DB source generated by this tool"),
            a("undo", "Undo", "undo", self.session.undo_step, "Ctrl+Z"),
            a("redo", "Redo", "redo", self.session.redo_step, "Ctrl+Y"),
            a("export", "Export", "export", self.export, tip="Excel and TIA Portal sources"),
            a("options", "Options", "options", self.options),
            a("help", "Help", "help", lambda: self.show_help(), "F1"),
        ]
        for action in window:
            self.addAction(action)
        # Editor commands: their single-key shortcuts only act inside the editor page.
        self.editor_actions = [
            a("pattern_new", "New Pattern", "pattern_new", self.new_pattern, tip="Add an empty pattern"),
            a("pattern_delete", "Delete Pattern", "pattern_delete", self.delete_pattern),
            a("change_id", "Change ID...", "change_id", self.change_id),
            a("source_view", "Source View", "source_view", self.source_view,
              tip="Show the PDF page and region this pattern was recognized from"),
            a("rotate_pattern", "Rotate Pattern", "rotate_pattern", lambda: None,
              tip="Rotate the whole pattern or create a rotated copy"),
            a("add", "Add Package", "add_package", self._toggle_add, tip="Click to place, R rotates",
              checkable=True),
            a("duplicate", "Duplicate", "duplicate", self.ctrl.duplicate_selected, "Ctrl+D"),
            a("rotate", "Rotate", "rotate_package", self.ctrl.rotate, "R", "Rotate selected packages by 90°"),
            a("delete", "Delete", "delete", self.ctrl.delete_selected, "Delete", "Delete selected packages"),
            a("fit", "Fit", "fit", lambda: self.ctrl.fit(False), "F"),
            a("fit_pallet", "Fit + Pallet", "fit_pallet", lambda: self.ctrl.fit(True), "Shift+F"),
            a("numeric", "Numeric", "numeric", self._toggle_numeric, tip="Symbolic or numeric dimensions",
              checkable=True),
            a("verify", "Verify", "verify", self.verify, "Ctrl+Return", "Verify the current pattern"),
            a("cancel", "Cancel Tool", "cancel", self._escape, "Esc"),
            a("select_all", "Select All", "fit", self.ctrl.select_all, "Ctrl+A"),
        ]
        self.act_numeric.setChecked(self.ctrl.display["numeric"])
        menu = QMenu(self)
        for label, turns, copy in (("Rotated copy 90°", 1, True), ("Rotated copy 180°", 2, True),
                                   ("Rotated copy 270°", 3, True), (None, 0, False),
                                   ("Rotate 90° (counter-clockwise)", 1, False),
                                   ("Rotate 180°", 2, False), ("Rotate 270° (clockwise 90°)", 3, False)):
            if label is None:
                menu.addSeparator()
                continue
            menu.addAction(label, lambda t=turns, c=copy: self.rotate_pattern(t, c))
        self.act_rotate_pattern.setMenu(menu)

    def _build_bar(self) -> None:
        bar = self.bar
        g = bar.add_group("Project")
        g.add_action(self.act_new)
        g.add_action(self.act_open)
        g.add_action(self.act_save, "small")
        g.add_action(self.act_save_as, "small")
        g.add_action(self.act_import_db, "small")
        g = bar.add_group("Edit")
        g.add_action(self.act_undo, "small")
        g.add_action(self.act_redo, "small")
        self.editor_groups = []
        g = bar.add_group("Pattern")
        g.add_action(self.act_pattern_new)
        g.add_action(self.act_rotate_pattern)
        g.add_action(self.act_change_id, "small")
        g.add_action(self.act_pattern_delete, "small")
        g.add_action(self.act_source_view, "small")
        self.editor_groups.append(g)
        g = bar.add_group("Package")
        g.add_action(self.act_add)
        g.add_action(self.act_duplicate, "small")
        g.add_action(self.act_rotate, "small")
        g.add_action(self.act_delete, "small")
        self.editor_groups.append(g)
        g = bar.add_group("View")
        g.add_action(self.act_fit, "small")
        g.add_action(self.act_fit_pallet, "small")
        g.add_action(self.act_numeric, "small")
        self.editor_groups.append(g)
        g = bar.add_group("Check")
        g.add_action(self.act_verify)
        self.editor_groups.append(g)
        self.pdf_groups = []
        for title, entries in self.pdf_workspace.ribbon_groups():
            g = bar.add_group(title)
            for action, size in entries:
                g.add_action(action, size)
            self.pdf_groups.append(g)
        bar.add_stretch()
        g = bar.add_group("Output")
        g.add_action(self.act_export)
        g = bar.add_group("Application")
        g.add_action(self.act_options, "small")
        g.add_action(self.act_help, "small")

    def _build_editor_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        for action in self.editor_actions:
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            page.addAction(action)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.patterns = PatternList(self.session)
        self.patterns.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.patterns.list.customContextMenuRequested.connect(self._pattern_menu)
        self.view = EditorView(self.ctrl)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._editor_menu)
        right = AppTabs()
        self.properties = PropertiesPanel(self.session, self.ctrl)
        self.properties.verifyRequested.connect(self.verify)
        self.properties.changeIdRequested.connect(self.change_id)
        self.properties.numeric.toggled.connect(self.act_numeric.setChecked)
        right.addTab(self.properties, "Properties")
        self.splitter.addWidget(self.patterns)
        self.splitter.addWidget(self.view)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([230, 900, 330])
        state = self.settings.splitter_state("editor")
        if state is not None:
            self.splitter.restoreState(state)
        layout.addWidget(self.splitter)
        self.editor_page = page
        return page

    def _editor_menu(self, pos) -> None:
        menu = QMenu(self)
        for action in (self.act_add, self.act_duplicate, self.act_rotate, self.act_delete, None,
                       self.act_fit, self.act_fit_pallet, None, self.act_verify):
            if action is None:
                menu.addSeparator()
            else:
                menu.addAction(action)
        menu.exec(self.view.mapToGlobal(pos))

    def _pattern_menu(self, pos) -> None:
        item = self.patterns.list.itemAt(pos)
        if item is not None:
            self.session.set_current(item.data(Qt.ItemDataRole.UserRole))
        menu = QMenu(self)
        menu.addAction(self.act_pattern_new)
        if item is not None:
            for action in (self.act_change_id, self.act_rotate_pattern, self.act_source_view,
                           self.act_verify, None, self.act_pattern_delete):
                if action is None:
                    menu.addSeparator()
                else:
                    menu.addAction(action)
        menu.exec(self.patterns.list.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------- state

    def _on_tab(self, index: int) -> None:
        editor = self.tabs.widget(index) is self.editor_page
        pdf = self.tabs.widget(index) is self.pdf_page
        for group in self.editor_groups:
            group.setVisible(editor)
        for group in self.pdf_groups:
            group.setVisible(pdf)
        if editor:
            self.view.setFocus()
        if self.tabs.widget(index) is self.help:
            self.help.show_topic()

    def _on_mode(self, mode: str) -> None:
        self.act_add.setChecked(mode == ADD)
        self._update_state()

    def _update_state(self) -> None:
        s = self.session
        has = s.has_project()
        pattern = s.current_pattern()
        selected = bool(self.ctrl.selected())
        for action in (self.act_save, self.act_save_as, self.act_pattern_new):
            action.setEnabled(has)
        self.act_source_view.setEnabled(pattern is not None and pattern.source is not None)
        for action in (self.act_pattern_delete, self.act_change_id, self.act_rotate_pattern, self.act_add,
                       self.act_fit, self.act_fit_pallet, self.act_select_all):
            action.setEnabled(pattern is not None)
        for action in (self.act_duplicate, self.act_rotate, self.act_delete):
            action.setEnabled(pattern is not None and selected)
        self.act_rotate.setEnabled(pattern is not None and (selected or self.ctrl.mode == ADD))
        report = s.report(pattern.uid) if pattern is not None else None
        self.act_verify.setEnabled(bool(report and report.valid and not is_verified(pattern)))
        self.act_undo.setEnabled(s.undo.can_undo())
        self.act_redo.setEnabled(s.undo.can_redo())
        self.act_undo.setText(f"Undo {s.undo.undo_label()}".strip())
        self.act_redo.setText(f"Redo {s.undo.redo_label()}".strip())
        blockers = s.export_blockers() if has else ["No project is open."]
        self.act_export.setEnabled(not blockers and not self.runner.busy("export"))
        self.act_export.setToolTip("Export Excel and TIA sources" if not blockers else
                                   "Export is available when every pattern is valid and verified.\n"
                                   + "\n".join(blockers))
        for index in (1, 2):
            self.tabs.setTabEnabled(index, has)
        name = s.project.name if has else ""
        mark = "*" if s.is_modified() else ""
        self.setWindowTitle(f"{name}{mark} - {APP_NAME}" if has else APP_NAME)

    # ------------------------------------------------------------- project

    def _confirm_discard(self) -> bool:
        """True if the current project may be replaced or closed."""
        if not self.pdf_workspace.confirm_discard_proposals():
            return False
        if not self.session.is_modified():
            return True
        answer = dialogs.ask_unsaved(self, f"Project '{self.session.project.name}'")
        if answer == "save":
            return self.save()
        return answer == "discard"

    def _start_project(self, project: Project, path: Path | None, message: str) -> None:
        self.session.replace_project(project, path)
        self.pdf_workspace.project_replaced()
        self.tabs.setCurrentWidget(self.editor_page)
        self.session.notify(message)

    def new_project(self) -> None:
        if self._confirm_discard():
            self._start_project(Project(name="Untitled"), None, "New project. Add a pattern or import PDFs.")

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open project", self.settings.last_dir("project"),
                                              PROJECT_FILTER)
        if path:
            self._open(Path(path))

    def open_path(self, path: str) -> None:
        if self._confirm_discard():
            self._open(Path(path))

    def _open(self, path: Path) -> None:
        try:
            project = project_store.load(path)
        except project_store.ProjectFileError as exc:
            self.session.notify(f"{path.name}: {exc}", "error")
            if not path.exists():
                self.settings.remove_recent_project(str(path))
                self.start.refresh()
            return
        self.settings.set_last_dir("project", str(path.parent))
        self.settings.add_recent_project(str(path))
        self.start.refresh()
        self._start_project(project, path, f"Opened {path.name}: {len(project.patterns)} patterns.")

    def save(self) -> bool:
        if not self.session.has_project():
            return False
        if self.session.path is None:
            return self.save_as()
        return self._write(self.session.path)

    def save_as(self) -> bool:
        if not self.session.has_project():
            return False
        start = str(self.session.path or Path(self.settings.last_dir("project") or Path.home())
                    / f"{self.session.project.name}{project_store.EXTENSION}")
        path, _ = QFileDialog.getSaveFileName(self, "Save project", start, PROJECT_FILTER)
        if not path:
            return False
        if not path.endswith(project_store.EXTENSION):
            path = path.removesuffix(".json") + project_store.EXTENSION
        return self._write(Path(path))

    def _write(self, path: Path) -> bool:
        project = self.session.project
        if project.name == "Untitled":
            # The first save names the project after its file; not an undoable edit.
            project = replace(project, name=project_store.display_name(path))
            self.session.project = project
        try:
            project_store.save(project, path)
        except OSError as exc:
            self.session.notify(f"Saving failed: {exc.strerror or exc}", "error", traceback.format_exc())
            return False
        self.session.mark_saved(path)
        self.settings.set_last_dir("project", str(path.parent))
        self.settings.add_recent_project(str(path))
        self.start.refresh()
        self.session.notify(f"Saved {path.name}.")
        return True

    def import_db(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import generated DB", self.settings.last_dir("export"),
                                              "TIA DB source (*.db);;All files (*)")
        if not path:
            return
        from layerforge.application.db_import import project_from_db
        from layerforge.infrastructure import tia_import
        try:
            imported = tia_import.read(path)
        except tia_import.DbImportError as exc:
            self.session.notify(str(exc), "error")
            return
        dialog = dialogs.DimensionsDialog(
            "Import generated DB",
            f"{len(imported.patterns)} patterns found in {imported.db_name}. Enter the example values "
            "used to display them (KL, KB and D are not stored in the DB).",
            self.settings.default_dimensions, self)
        if dialog.exec() != dialogs.QDialog.DialogCode.Accepted:
            return
        project = project_from_db(imported, dialog.dimensions(), Path(path).stem)
        self._start_project(project, None, f"Imported {len(project.patterns)} patterns. "
                                           "All are unverified - check and verify each one.")

    # ------------------------------------------------------------- patterns

    def new_pattern(self) -> None:
        if not self.session.has_project():
            return
        dims = self.settings.default_dimensions
        if self.session.execute("New pattern", lambda p: ops.add_pattern(p, dims=dims)):
            self.tabs.setCurrentWidget(self.editor_page)
            QTimer.singleShot(0, self.ctrl.start_add)

    def delete_pattern(self) -> None:
        pattern = self.session.current_pattern()
        if pattern is None:
            return
        strong = is_verified(pattern) or pattern.origin == Origin.DB_IMPORT
        detail = ("This pattern is verified or came from a PLC DB; the PLC may use PatternId "
                  f"{pattern.pattern_id}." if strong else "")
        if dialogs.confirm(self, "Delete pattern", f"Delete pattern {pattern.pattern_id}?", detail, strong,
                           ok_text="Delete"):
            self.session.execute(f"Delete pattern {pattern.pattern_id}",
                                 lambda p: ops.delete_pattern(p, pattern.uid))

    def change_id(self) -> None:
        pattern = self.session.current_pattern()
        if pattern is None:
            return
        used = {p.pattern_id for p in self.session.project.patterns}
        dialog = dialogs.ChangeIdDialog(pattern, used, self)
        if dialog.exec() == dialogs.QDialog.DialogCode.Accepted:
            new_id = dialog.value()
            self.session.execute(f"Change PatternId to {new_id}",
                                 lambda p: ops.change_pattern_id(p, pattern.uid, new_id))

    def rotate_pattern(self, turns: int, copy: bool) -> None:
        pattern = self.session.current_pattern()
        if pattern is None or not pattern.packages:
            return
        degrees = turns * 90
        if copy:
            if self.session.execute(f"Rotated copy {degrees}°",
                                    lambda p: ops.rotated_copy(p, pattern.uid, turns)):
                report = self.session.report(self.session.current_uid)
                twin = report is not None and any(i.code == "duplicate-geometry" for i in report.issues)
                self.session.notify(f"Rotated copy created as pattern {self.session.current_pattern().pattern_id}."
                                    + (" It is identical to an existing pattern." if twin else ""),
                                    "warning" if twin else "info")
        else:
            self.session.execute(f"Rotate pattern {degrees}°",
                                 lambda p: ops.rotate_pattern(p, pattern.uid, turns))

    def source_view(self) -> None:
        pattern = self.session.current_pattern()
        if pattern is not None and self.pdf_workspace.show_source(pattern):
            self.tabs.setCurrentWidget(self.pdf_page)

    def verify(self) -> None:
        pattern = self.session.current_pattern()
        if pattern is None:
            return
        report = self.session.report(pattern.uid)
        if report is None or not report.valid:
            self.session.notify("The pattern cannot be verified: "
                                + " ".join(i.message for i in (report.blockers if report else [])), "warning")
            return
        if is_verified(pattern):
            self.session.notify(f"Pattern {pattern.pattern_id} is already verified.")
            return
        if dialogs.VerifyDialog(pattern, report, self).exec() == dialogs.QDialog.DialogCode.Accepted:
            self.session.execute(f"Verify pattern {pattern.pattern_id}", lambda p: ops.verify(p, pattern.uid))
            self.session.notify(f"Pattern {pattern.pattern_id} verified.")

    # ------------------------------------------------------------- editor glue

    def _toggle_add(self) -> None:
        if self.ctrl.mode == ADD:
            self.ctrl.cancel()
        else:
            self.ctrl.start_add()
        self.view.setFocus()

    def _toggle_numeric(self) -> None:
        self.properties.set_numeric(self.act_numeric.isChecked())

    def _escape(self) -> None:
        self.ctrl.cancel()

    # ------------------------------------------------------------- output

    def export(self) -> None:
        blockers = self.session.export_blockers()
        if blockers:
            self.session.notify("Export not possible. " + " ".join(blockers), "warning")
            return
        dialog = dialogs.ExportDialog(self.session.project.name, self.settings, self)
        if dialog.exec() != dialogs.QDialog.DialogCode.Accepted:
            return
        from layerforge.application import export_service
        from layerforge.domain.export_model import build_snapshot
        # The snapshot is taken now: edits made while the files are written do not leak in.
        snapshot = build_snapshot(self.session.project, self.settings.tia_names, datetime.now())
        request = dialog.request()

        def job(_cancel, _progress):
            return export_service.export(snapshot, request)

        def done(files):
            self._update_state()
            self.session.notify(f"Exported {len(files)} files to {files[0].parent}: "
                                + ", ".join(f.name for f in files))

        def failed(message, details):
            self._update_state()
            self.session.notify(message, "error", details)

        self.runner.start("export", job, done, failed)
        self._update_state()
        self.session.notify("Exporting...")

    def options(self) -> None:
        dialog = dialogs.OptionsDialog(self.settings, self)
        if dialog.exec() == dialogs.QDialog.DialogCode.Accepted:
            self.session.set_max_packages(self.settings.max_packages)
            self._update_state()
            self.session.notify("Options saved. A theme change applies after a restart.")

    def show_help(self, anchor: str = "") -> None:
        if not anchor:
            current = self.tabs.currentWidget()
            anchor = "editor" if current is self.editor_page else "pdf" if current is self.pdf_page else ""
        self.tabs.setCurrentWidget(self.help)
        self.help.show_topic(anchor)

    # ------------------------------------------------------------- window

    def showEvent(self, event) -> None:
        super().showEvent(event)
        dark_title_bar(self, self.settings.theme == "dark")

    def closeEvent(self, event) -> None:
        if not self._confirm_discard():
            event.ignore()
            return
        self.runner.shutdown()
        self.settings.set_window_geometry(self.saveGeometry())
        self.settings.set_splitter_state("editor", self.splitter.saveState())
        self.settings.sync()
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.status.sync_geometry()
