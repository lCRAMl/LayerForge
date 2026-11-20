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
from .geometry import corner_relative, extent, validity_conditions
from .linear import LinearForm
from .model import MAX_PATTERN_ID, NAME_LENGTH, Pattern, Project
from .sequence import auto_order

FORMAT_NAME = "LayerPattern-TIA"
FORMAT_VERSION = 1

# Pattern names go into a TIA string literal, so quote and dollar sign (the SCL
# escape character) are excluded; letters, digits and a few separators remain.
_NAME_CHARS = "A-Za-z0-9_\\-./+#"
_PATTERN_NAME = re.compile(rf"^[{_NAME_CHARS}](?:[{_NAME_CHARS} ]*[{_NAME_CHARS}])?$")

# Words that must not be used as TIA identifiers. Not exhaustive; it catches the
# names someone might plausibly type into the options dialog.
_RESERVED = {
    "ARRAY", "AUTHOR", "BEGIN", "BOOL", "BY", "CASE", "CONST", "DATA_BLOCK", "DINT", "DO", "ELSE",
    "FAMILY", "NAME", "OK", "TITLE",
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


def pattern_name_problem(name: str) -> str | None:
    """Why `name` cannot be a pattern name, or None. An empty name is reported elsewhere."""
    if len(name) > NAME_LENGTH:
        return f"The name is longer than {NAME_LENGTH} characters."
    if not _PATTERN_NAME.match(name):
        return ("The name may contain letters, digits, spaces and - _ . / + # "
                "(no space at the start or end).")
    return None


def same_name(a: str, b: str) -> bool:
    """Names are compared without case so 'eu13' and 'EU13' cannot both exist."""
    return a.casefold() == b.casefold()


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
    position: int            # 1-based position within the pattern; NOT a placement order
    orientation: int
    kx: LinearForm
    ky: LinearForm


@dataclass(frozen=True, slots=True)
class PatternRow:
    pattern_id: int
    first_index: int
    count: int
    name: str = ""
    # Documentation for the PLC side (Excel only, not in the DB):
    width: LinearForm = LinearForm()          # outline along X, e.g. 3*KL + 2*D
    height: LinearForm = LinearForm()
    valid_while: tuple[str, ...] = ()         # e.g. "3*KL >= 4*KB + D"


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
    """(orientation, x, y) relative to the lower-left corner, in the automatic order."""
    packages = auto_order(pattern.packages, pattern.dims)
    corners = corner_relative(packages, pattern.dims)
    return [(p.orientation, x, y) for p, (x, y) in zip(packages, corners)]


def fingerprint(pattern: Pattern) -> str:
    """Hash of everything the PLC receives for this pattern (decision D10)."""
    lines = [f"id={pattern.pattern_id}", f"name={pattern.name}"]
    for position, (orientation, x, y) in enumerate(package_rows(pattern), start=1):
        coeffs = ",".join(str(c) for c in x.coefficients() + y.coefficients())
        lines.append(f"{position}:{orientation}:{coeffs}")
    return hashlib.sha1("\n".join(lines).encode("utf-8")).hexdigest()


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
        for position, (orientation, x, y) in enumerate(package_rows(pattern), start=1):
            for coeff in x.coefficients() + y.coefficients():
                rational.check(coeff)
            packages.append(PackageRow(len(packages) + 1, pattern.pattern_id, position,
                                       orientation, x, y))
        box = extent(pattern.packages, pattern.dims)
        conditions = tuple(c.text("*", ">=") for c in validity_conditions(pattern.packages, pattern.dims))
        patterns.append(PatternRow(pattern.pattern_id, first, len(pattern.packages), pattern.name,
                                   box.width(), box.height(), conditions))
    return ExportSnapshot(project.name, generated_at, names, tuple(patterns), tuple(packages))
