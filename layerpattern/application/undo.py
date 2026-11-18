"""Undo/redo by whole-project snapshots (decision D6).

Projects are immutable and share unchanged patterns, so keeping the state before and
after every command costs almost nothing and undo can never get out of step with the
data: there are no inverse operations to get wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

from layerpattern.domain.model import Project


@dataclass(frozen=True, slots=True)
class Step:
    label: str
    before: Project
    after: Project
    focus: int | None = None      # pattern uid to show after undo/redo


class UndoStack:
    def __init__(self, limit: int = 300) -> None:
        self._steps: list[Step] = []
        self._index = 0            # number of steps currently applied
        self._clean: int | None = 0
        self._limit = limit

    def push(self, step: Step) -> None:
        del self._steps[self._index:]
        if self._clean is not None and self._clean > self._index:
            self._clean = None     # the saved state can no longer be reached
        self._steps.append(step)
        if len(self._steps) > self._limit:
            self._steps.pop(0)
            self._clean = None if self._clean in (None, 0) else self._clean - 1
        self._index = len(self._steps)

    def can_undo(self) -> bool:
        return self._index > 0

    def can_redo(self) -> bool:
        return self._index < len(self._steps)

    def undo_label(self) -> str:
        return self._steps[self._index - 1].label if self.can_undo() else ""

    def redo_label(self) -> str:
        return self._steps[self._index].label if self.can_redo() else ""

    def undo(self) -> Step:
        if not self.can_undo():
            raise IndexError("nothing to undo")
        self._index -= 1
        return self._steps[self._index]

    def redo(self) -> Step:
        if not self.can_redo():
            raise IndexError("nothing to redo")
        self._index += 1
        return self._steps[self._index - 1]

    def clear(self) -> None:
        self._steps.clear()
        self._index = 0
        self._clean = 0

    def mark_clean(self) -> None:
        """The current state has been saved."""
        self._clean = self._index

    def is_clean(self) -> bool:
        return self._clean == self._index
