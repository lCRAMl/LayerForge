"""What leaves the tool: per package BaseOrientation and six coefficients.

`ExportSnapshot` is the single immutable input for every exporter (Excel and TIA),
so both files are guaranteed to describe the same data.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

from . import rational
from .geometry import relative_centers
from .linear import LinearForm
from .model import MAX_PATTERN_ID, Pattern, Project

FORMAT_NAME = "LayerPattern-TIA"
FORMAT_VERSION = 1

# Words that must not be used as TIA identifiers. Not exhaustive; it catches the
# names someone might plausibly type into the options dialog.
_RESERVED = {
    "ARRAY", "BEGIN", "BOOL", "BY", "CASE", "CONST", "DATA_BLOCK", "DINT", "DO", "ELSE",
    "END_DATA_BLOCK", "END_STRUCT", "END_TYPE", "END_VAR", "FALSE", "FOR", "FUNCTION",
    "FUNCTION_BLOCK", "IF", "INT", "NON_RETAIN", "OF", "REAL", "RETAIN", "STRUCT", "THEN",
    "TO", "TRUE", "TYPE", "UINT", "USINT", "VAR", "VERSION", "WHILE",
}
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def tia_name_problem(name: str) -> str | None:
    if not _IDENT.match(name):
        return f"'{name}' is not a valid name (letters, digits, underscore; must not start with a digit)."
    if name.upper() in _RESERVED:
        return f"'{name}' is a reserved word."
    return None


@dataclass(frozen=True, slots=True)
class TiaNames:
    """Naming set A (decision D20)."""

    package_type: str = "UDT_LayerPackage"
    index_type: str = "UDT_LayerPatternIndex"
    db: str = "DB_LayerPatterns"

    def problems(self) -> list[str]:
        out = [p for p in map(tia_name_problem, (self.package_type, self.index_type, self.db)) if p]
        if len({self.package_type.upper(), self.index_type.upper(), self.db.upper()}) < 3:
            out.append("Type and DB names must be different.")
        return out


@dataclass(frozen=True, slots=True)
class PackageRow:
    global_index: int        # 1-based position in the flat package array
    pattern_id: int
    sequence: int            # 1-based placement order within the pattern
    orientation: int
    kx: LinearForm
    ky: LinearForm


@dataclass(frozen=True, slots=True)
class PatternRow:
    pattern_id: int
    first_index: int
    count: int


@dataclass(frozen=True, slots=True)
class ExportSnapshot:
    project_name: str
    generated_at: datetime
    names: TiaNames
    patterns: tuple[PatternRow, ...]      # ascending PatternId
    packages: tuple[PackageRow, ...]      # flat array order

    def index_table(self) -> list[tuple[int, int]]:
        """(FirstPackageIndex, PackageCount) for PatternId 1..99; (0, 0) = no pattern."""
        table = [(0, 0)] * MAX_PATTERN_ID
        for row in self.patterns:
            table[row.pattern_id - 1] = (row.first_index, row.count)
        return table


def package_rows(pattern: Pattern) -> list[tuple[int, LinearForm, LinearForm]]:
    """(orientation, x, y) relative to the pattern centre, in placement order."""
    centers = relative_centers(pattern.packages, pattern.dims)
    return [(p.orientation, x, y) for p, (x, y) in zip(pattern.packages, centers)]


def fingerprint(pattern: Pattern) -> str:
    """Hash of everything the PLC receives for this pattern (decision D10)."""
    lines = [f"id={pattern.pattern_id}"]
    for sequence, (orientation, x, y) in enumerate(package_rows(pattern), start=1):
        coeffs = ",".join(str(c) for c in x.coefficients() + y.coefficients())
        lines.append(f"{sequence}:{orientation}:{coeffs}")
    return hashlib.sha1("\n".join(lines).encode("ascii")).hexdigest()


def is_verified(pattern: Pattern) -> bool:
    if pattern.verified is None or not pattern.packages or not pattern.dims.is_valid():
        return False
    return pattern.verified == fingerprint(pattern)


def build_snapshot(project: Project, names: TiaNames, generated_at: datetime) -> ExportSnapshot:
    """Flat export data. The caller has checked that every pattern is valid and verified."""
    patterns: list[PatternRow] = []
    packages: list[PackageRow] = []
    for pattern in sorted(project.patterns, key=lambda p: p.pattern_id):
        first = len(packages) + 1
        for sequence, (orientation, x, y) in enumerate(package_rows(pattern), start=1):
            for coeff in x.coefficients() + y.coefficients():
                rational.check(coeff)
            packages.append(PackageRow(len(packages) + 1, pattern.pattern_id, sequence,
                                       orientation, x, y))
        patterns.append(PatternRow(pattern.pattern_id, first, len(pattern.packages)))
    return ExportSnapshot(project.name, generated_at, names, tuple(patterns), tuple(packages))
