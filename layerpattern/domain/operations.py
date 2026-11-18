"""Project-level edits as pure functions `Project -> Project`.

These are the building blocks of the undoable commands; they validate their own
preconditions and raise `OperationError` with a user-facing message otherwise.
"""

from __future__ import annotations

from dataclasses import replace

from .export_model import fingerprint
from .model import (
    MAX_PATTERN_ID, MIN_PATTERN_ID, Dimensions, Origin, Package, Pattern, PdfRef, Project,
    SourceRef
)
from .transform import rotate_packages


class OperationError(ValueError):
    """An edit was refused; the message is meant for the status bar."""


def next_pattern_id(project: Project) -> int | None:
    """Highest PatternId + 1 (spec). If 99 is taken, the lowest free ID; None if all are used."""
    used = {p.pattern_id for p in project.patterns}
    candidate = max(used, default=0) + 1
    if candidate <= MAX_PATTERN_ID:
        return candidate
    free = [i for i in range(MIN_PATTERN_ID, MAX_PATTERN_ID + 1) if i not in used]
    return free[0] if free else None


def add_pattern(project: Project, packages=(), dims: Dimensions | None = None,
                pattern_id: int | None = None, source: SourceRef | None = None,
                origin: str = Origin.MANUAL, index: int | None = None) -> tuple[Project, int]:
    """Append (or insert at `index`) a new pattern; returns the project and the new uid."""
    if pattern_id is None:
        pattern_id = next_pattern_id(project)
        if pattern_id is None:
            raise OperationError(f"All PatternIds {MIN_PATTERN_ID}..{MAX_PATTERN_ID} are in use.")
    elif any(p.pattern_id == pattern_id for p in project.patterns):
        raise OperationError(f"PatternId {pattern_id} is already in use.")
    pattern = Pattern(project.next_uid, pattern_id, tuple(packages), dims or Dimensions(),
                      None, source, origin)
    patterns = list(project.patterns)
    patterns.insert(len(patterns) if index is None else index, pattern)
    return replace(project, patterns=tuple(patterns), next_uid=project.next_uid + 1), pattern.uid


def delete_pattern(project: Project, uid: int) -> Project:
    project.index_of(uid)
    return replace(project, patterns=tuple(p for p in project.patterns if p.uid != uid))


def change_pattern_id(project: Project, uid: int, new_id: int) -> Project:
    if not MIN_PATTERN_ID <= new_id <= MAX_PATTERN_ID:
        raise OperationError(f"PatternId must be between {MIN_PATTERN_ID} and {MAX_PATTERN_ID}.")
    if any(p.pattern_id == new_id and p.uid != uid for p in project.patterns):
        raise OperationError(f"PatternId {new_id} is already in use.")
    pattern = project.pattern(uid)
    if pattern.pattern_id == new_id:
        return project
    return project.with_pattern(replace(pattern, pattern_id=new_id, verified=None))


def set_packages(project: Project, uid: int, packages) -> Project:
    """New geometry or sequence; drops verification."""
    return project.with_pattern(project.pattern(uid).with_packages(packages))


def set_dimensions(project: Project, uid: int, dims: Dimensions) -> Project:
    """Example values only: verification is kept (it is re-checked by fingerprint)."""
    problems = dims.problems()
    if problems:
        raise OperationError(" ".join(problems))
    return project.with_pattern(replace(project.pattern(uid), dims=dims))


def verify(project: Project, uid: int) -> Project:
    """Mark as verified. The caller has shown the summary and checked validity."""
    pattern = project.pattern(uid)
    return project.with_pattern(replace(pattern, verified=fingerprint(pattern)))


def move_in_list(project: Project, uid: int, target_index: int) -> Project:
    """Manual list order (drag and drop); has no effect on the export."""
    patterns = list(project.patterns)
    pattern = patterns.pop(project.index_of(uid))
    patterns.insert(max(0, min(target_index, len(patterns))), pattern)
    return replace(project, patterns=tuple(patterns))


def rotate_pattern(project: Project, uid: int, quarter_turns: int) -> Project:
    pattern = project.pattern(uid)
    return set_packages(project, uid, rotate_packages(pattern.packages, quarter_turns, pattern.dims))


def rotated_copy(project: Project, uid: int, quarter_turns: int) -> tuple[Project, int]:
    """Rotated copy with a new PatternId, inserted right after the original in the list."""
    pattern = project.pattern(uid)
    packages = rotate_packages(pattern.packages, quarter_turns, pattern.dims)
    return add_pattern(project, packages, pattern.dims, index=project.index_of(uid) + 1)


def replace_geometry(project: Project, uid: int, packages: tuple[Package, ...],
                     source: SourceRef | None) -> Project:
    """Re-recognition result explicitly accepted over an existing pattern (decision D17)."""
    pattern = project.pattern(uid)
    return project.with_pattern(replace(pattern.with_packages(packages), source=source,
                                        origin=Origin.RECOGNIZED))


def add_pdf(project: Project, path: str) -> tuple[Project, int]:
    """Register a PDF path once; returns the existing id if the path is already known."""
    for ref in project.pdfs:
        if ref.path == path:
            return project, ref.pdf_id
    pdf_id = max((ref.pdf_id for ref in project.pdfs), default=0) + 1
    return replace(project, pdfs=project.pdfs + (PdfRef(pdf_id, path),)), pdf_id


def relink_pdf(project: Project, pdf_id: int, path: str) -> Project:
    if project.pdf(pdf_id) is None:
        raise OperationError("Unknown PDF reference.")
    pdfs = tuple(PdfRef(r.pdf_id, path) if r.pdf_id == pdf_id else r for r in project.pdfs)
    return replace(project, pdfs=pdfs)
