"""Structural validation of patterns and of the whole project.

Blocking issues prevent verification and export; notes are informational. All
geometric checks use the pattern's current example values (spec: "validity scope").
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import rational
from .duplicates import compare
from .export_model import fingerprint, package_rows
from .geometry import (
    Condition, clearance_pairs, components, neighbour_pairs, overlapping_pairs, rects,
    validity_conditions
)
from .model import MAX_PATTERN_ID, MIN_PATTERN_ID, ORIENTATIONS, Pattern, Project

# Blocking
INVALID_DIMENSIONS = "invalid-dimensions"
EMPTY = "empty"
TOO_MANY = "too-many-packages"
BAD_ORIENTATION = "bad-orientation"
OVERLAP = "overlap"
CLEARANCE = "clearance"
DISCONNECTED = "disconnected"
NOT_REPRESENTABLE = "not-representable"
ID_RANGE = "id-range"
DUPLICATE_ID = "duplicate-id"
DUPLICATE_GEOMETRY = "duplicate-geometry"
# Notes
SQUARE_PACKAGE = "square-package"
MIRROR_SIMILAR = "mirror-similar"
VERIFICATION_STALE = "verification-stale"


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    message: str
    blocking: bool
    packages: tuple[int, ...] = ()        # zero-based package indexes concerned
    patterns: tuple[int, ...] = ()        # uids of other patterns concerned


@dataclass(frozen=True, slots=True)
class PatternReport:
    issues: tuple[Issue, ...] = ()
    conditions: tuple[Condition, ...] = field(default=())

    @property
    def valid(self) -> bool:
        return not any(issue.blocking for issue in self.issues)

    @property
    def blockers(self) -> list[Issue]:
        return [i for i in self.issues if i.blocking]

    @property
    def notes(self) -> list[Issue]:
        return [i for i in self.issues if not i.blocking]

    def has(self, code: str) -> bool:
        return any(issue.code == code for issue in self.issues)


def _numbers(indexes) -> str:
    return ", ".join(f"#{i + 1}" for i in sorted(indexes))


def check_pattern(pattern: Pattern, max_packages: int) -> PatternReport:
    """Checks that only need the pattern itself."""
    issues: list[Issue] = []
    if not MIN_PATTERN_ID <= pattern.pattern_id <= MAX_PATTERN_ID:
        issues.append(Issue(ID_RANGE, f"PatternId must be between {MIN_PATTERN_ID} and "
                                      f"{MAX_PATTERN_ID}.", True))
    problems = pattern.dims.problems()
    if problems:
        issues.append(Issue(INVALID_DIMENSIONS, " ".join(problems), True))
        return PatternReport(tuple(issues))
    packages = pattern.packages
    if not packages:
        issues.append(Issue(EMPTY, "The pattern has no packages.", True))
        return PatternReport(tuple(issues))
    if len(packages) > max_packages:
        issues.append(Issue(TOO_MANY, f"{len(packages)} packages exceed the maximum of "
                                      f"{max_packages}.", True))
    bad = [i for i, p in enumerate(packages) if p.orientation not in ORIENTATIONS]
    if bad:
        issues.append(Issue(BAD_ORIENTATION, f"Invalid BaseOrientation at {_numbers(bad)}.", True,
                            tuple(bad)))
        return PatternReport(tuple(issues))

    try:
        boxes = rects(packages, pattern.dims)
        rows = package_rows(pattern)
    except ValueError:
        issues.append(Issue(NOT_REPRESENTABLE, "A package position is not an exact multiple "
                                               "of 1/16 KL, KB or D.", True))
        return PatternReport(tuple(issues))

    odd = [i for i, (_o, x, y) in enumerate(rows)
           if not all(rational.is_representable(c) for c in x.coefficients() + y.coefficients())]
    if odd:
        issues.append(Issue(NOT_REPRESENTABLE, f"Coefficients of {_numbers(odd)} cannot be "
                                               f"exported exactly.", True, tuple(odd)))

    overlaps = overlapping_pairs(boxes)
    if overlaps:
        involved = {k for pair in overlaps for k in pair}
        issues.append(Issue(OVERLAP, f"Packages overlap: {_numbers(involved)}.", True,
                            tuple(sorted(involved))))
    close = clearance_pairs(boxes, pattern.dims)
    if close:
        involved = {k for pair in close for k in pair}
        issues.append(Issue(CLEARANCE, f"Gap smaller than D between {_numbers(involved)}.", True,
                            tuple(sorted(involved))))
    groups = components(len(packages), neighbour_pairs(boxes, pattern.dims))
    if len(groups) > 1:
        main = max(groups, key=len)
        loose = sorted(k for g in groups if g is not main for k in g)
        issues.append(Issue(DISCONNECTED, f"Not connected to the rest of the pattern: "
                                          f"{_numbers(loose)}.", True, tuple(loose)))

    if pattern.dims.kl == pattern.dims.kb:
        issues.append(Issue(SQUARE_PACKAGE, "KL equals KB: the orientation is geometrically "
                                            "indeterminate and is exported as 0.", False))
    if pattern.verified is not None and pattern.verified != fingerprint(pattern):
        issues.append(Issue(VERIFICATION_STALE, "The current example values change the exported "
                                                "coefficients; the pattern must be verified again.",
                            False))
    return PatternReport(tuple(issues), tuple(validity_conditions(packages, pattern.dims)))


def check_project(project: Project, max_packages: int) -> dict[int, PatternReport]:
    """Pattern checks plus everything that depends on other patterns."""
    reports = {p.uid: check_pattern(p, max_packages) for p in project.patterns}
    by_id: dict[int, list[int]] = {}
    for p in project.patterns:
        by_id.setdefault(p.pattern_id, []).append(p.uid)
    # Only patterns whose coefficients can be computed take part in the comparison.
    unusable = (INVALID_DIMENSIONS, EMPTY, BAD_ORIENTATION, NOT_REPRESENTABLE)
    candidates = [p for p in project.patterns
                  if not any(reports[p.uid].has(code) for code in unusable)]
    duplicates, similar = compare(candidates)
    ids = {p.uid: p.pattern_id for p in project.patterns}

    for p in project.patterns:
        extra: list[Issue] = []
        same_id = [u for u in by_id[p.pattern_id] if u != p.uid]
        if same_id:
            extra.append(Issue(DUPLICATE_ID, f"PatternId {p.pattern_id} is used more than once.",
                               True, patterns=tuple(same_id)))
        if p.uid in duplicates:
            others = duplicates[p.uid]
            extra.append(Issue(DUPLICATE_GEOMETRY, "Identical geometry to pattern "
                               + ", ".join(str(ids[u]) for u in others) + ".", True,
                               patterns=tuple(others)))
        if p.uid in similar:
            others = similar[p.uid]
            extra.append(Issue(MIRROR_SIMILAR, "Mirror image of pattern "
                               + ", ".join(str(ids[u]) for u in others) + ".", False,
                               patterns=tuple(others)))
        if extra:
            report = reports[p.uid]
            reports[p.uid] = PatternReport(report.issues + tuple(extra), report.conditions)
    return reports
