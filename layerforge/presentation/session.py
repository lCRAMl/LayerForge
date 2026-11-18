"""The open project as seen by the user interface.

All edits go through `execute()`: a pure function turns the current project into a
new one, the step is pushed on the undo stack and every view is told old and new
project. Views compare pattern objects by identity to update only what changed.
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal

from layerforge.application.undo import Step, UndoStack
from layerforge.application.validator import ProjectValidator
from layerforge.domain.model import Project
from layerforge.domain.operations import OperationError
from layerforge.domain.validation import PatternReport
from layerforge.presentation.settings import AppSettings

Edit = Callable[[Project], "Project | tuple[Project, int]"]


class ProjectSession(QObject):
    projectChanged = pyqtSignal(object, object)     # old, new (either may be None)
    currentChanged = pyqtSignal(object)             # pattern uid or None
    stateChanged = pyqtSignal()                     # path, modified flag, undo availability
    message = pyqtSignal(str, str, str)             # text, level, details

    def __init__(self, settings: AppSettings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.project: Project | None = None
        self.path: Path | None = None
        self.undo = UndoStack()
        self.validator = ProjectValidator(settings.max_packages)
        self.current_uid: int | None = None

    # --- state -------------------------------------------------------------

    def has_project(self) -> bool:
        return self.project is not None

    def is_modified(self) -> bool:
        return self.project is not None and not self.undo.is_clean()

    def reports(self) -> dict[int, PatternReport]:
        return self.validator.reports(self.project) if self.project else {}

    def report(self, uid: int) -> PatternReport | None:
        return self.reports().get(uid)

    def export_blockers(self) -> list[str]:
        if self.project is None:
            return ["No project is open."]
        return self.validator.export_blockers(self.project)

    def current_pattern(self):
        if self.project is None or self.current_uid is None:
            return None
        try:
            return self.project.pattern(self.current_uid)
        except KeyError:
            return None

    def set_current(self, uid: int | None) -> None:
        if uid == self.current_uid:
            return
        self.current_uid = uid
        self.currentChanged.emit(uid)

    def notify(self, text: str, level: str = "info", details: str = "") -> None:
        self.message.emit(text, level, details)

    def set_max_packages(self, value: int) -> None:
        self.validator.set_max_packages(value)
        if self.project is not None:
            self.projectChanged.emit(self.project, self.project)

    # --- editing -----------------------------------------------------------

    def execute(self, label: str, edit: Edit, focus: int | None = None) -> bool:
        """Apply `edit`; refused edits only produce a status message. Returns success."""
        if self.project is None:
            return False
        before = self.project
        try:
            result = edit(before)
        except OperationError as exc:
            self.notify(str(exc), "warning")
            return False
        except Exception as exc:  # noqa: BLE001 - keep the GUI alive, report details
            self.notify(f"{label} failed: {exc}", "error", traceback.format_exc())
            return False
        after, new_uid = result if isinstance(result, tuple) else (result, None)
        if after is before:
            return False
        target = new_uid if new_uid is not None else (focus if focus is not None else self.current_uid)
        self.undo.push(Step(label, before, after, target))
        self._apply(before, after, target)
        return True

    def undo_step(self) -> None:
        if self.undo.can_undo():
            step = self.undo.undo()
            self._apply(step.after, step.before, step.focus)
            self.notify(f"Undone: {step.label}")

    def redo_step(self) -> None:
        if self.undo.can_redo():
            step = self.undo.redo()
            self._apply(step.before, step.after, step.focus)
            self.notify(f"Redone: {step.label}")

    def _apply(self, old: Project | None, new: Project | None, focus: int | None) -> None:
        self.project = new
        self.projectChanged.emit(old, new)
        uids = {p.uid for p in new.patterns} if new else set()
        if focus in uids:
            self.set_current(focus)
        elif self.current_uid not in uids:
            self.set_current(new.patterns[0].uid if new and new.patterns else None)
        self.stateChanged.emit()

    # --- whole projects ----------------------------------------------------

    def replace_project(self, project: Project | None, path: Path | None) -> None:
        """New, opened or imported project; the undo history starts fresh."""
        old = self.project
        self.undo.clear()
        self.path = path
        self.current_uid = None
        self._apply(old, project, project.patterns[0].uid if project and project.patterns else None)

    def mark_saved(self, path: Path) -> None:
        self.path = path
        self.undo.mark_clean()
        self.stateChanged.emit()

    def rename(self, name: str) -> None:
        from dataclasses import replace
        self.execute("Rename project", lambda p: replace(p, name=name) if name != p.name else p)
