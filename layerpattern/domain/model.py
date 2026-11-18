"""Immutable domain model.

Every edit produces a new object; unchanged parts are shared. That makes undo a
matter of keeping the previous `Project` and lets views detect changes by identity.

Pattern coordinates: X to the right, Y upwards. A package position is the centre
of the package as a `LinearForm`; the origin is arbitrary (normally the lower-left
corner of the pattern's bounding box). Exported coefficients are always taken
relative to the bounding-box centre, so the origin never leaks into the PLC data.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .linear import KB, KL, LinearForm

ORIENTATIONS = (0, 90)       # 0: KL along X, 90: KL along Y
MIN_PATTERN_ID = 1
MAX_PATTERN_ID = 99
DEFAULT_MAX_PACKAGES = 64


class Origin:
    MANUAL = "manual"
    RECOGNIZED = "recognized"
    DB_IMPORT = "db-import"
    ALL = (MANUAL, RECOGNIZED, DB_IMPORT)


@dataclass(frozen=True, slots=True)
class Package:
    x: LinearForm
    y: LinearForm
    orientation: int = 0

    def half_width(self) -> LinearForm:
        return (KL if self.orientation == 0 else KB).half()

    def half_height(self) -> LinearForm:
        return (KB if self.orientation == 0 else KL).half()

    def left(self) -> LinearForm:
        return self.x - self.half_width()

    def right(self) -> LinearForm:
        return self.x + self.half_width()

    def bottom(self) -> LinearForm:
        return self.y - self.half_height()

    def top(self) -> LinearForm:
        return self.y + self.half_height()

    def moved(self, dx: LinearForm, dy: LinearForm) -> Package:
        return replace(self, x=self.x + dx, y=self.y + dy)

    def toggled(self) -> Package:
        """Same centre, the other orientation."""
        return replace(self, orientation=90 if self.orientation == 0 else 0)


@dataclass(frozen=True, slots=True)
class Dimensions:
    """Project-only example values in whole millimetres. Never exported."""

    kl: int = 600
    kb: int = 400
    d: int = 20
    pallet_x: int = 1200     # pallet "width", horizontal
    pallet_y: int = 800      # pallet "length", vertical

    def problems(self) -> list[str]:
        out = []
        if self.kl <= 0:
            out.append("KL must be greater than 0.")
        if self.kb <= 0:
            out.append("KB must be greater than 0.")
        if self.kl < self.kb:
            out.append("KL must not be smaller than KB.")
        if self.d < 0:
            out.append("D must not be negative.")
        if self.pallet_x <= 0 or self.pallet_y <= 0:
            out.append("Pallet dimensions must be greater than 0.")
        return out

    def is_valid(self) -> bool:
        return not self.problems()


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Where an accepted pattern came from: PDF, zero-based page, region in PDF points."""

    pdf_id: int
    page: int
    rect: tuple[float, float, float, float]   # x0, y0, x1, y1; origin top-left of the page


@dataclass(frozen=True, slots=True)
class Pattern:
    uid: int                                  # internal identity; survives PatternId changes
    pattern_id: int
    packages: tuple[Package, ...] = ()       # order == placement sequence
    dims: Dimensions = field(default_factory=Dimensions)
    verified: str | None = None              # fingerprint of the exported data when verified
    source: SourceRef | None = None
    origin: str = Origin.MANUAL

    def with_packages(self, packages) -> Pattern:
        """New geometry or sequence. Changes exported data, so verification is dropped."""
        return replace(self, packages=tuple(packages), verified=None)


@dataclass(frozen=True, slots=True)
class PdfRef:
    pdf_id: int
    path: str


@dataclass(frozen=True, slots=True)
class Project:
    name: str = "Untitled"
    patterns: tuple[Pattern, ...] = ()       # manual list order; export order is by PatternId
    pdfs: tuple[PdfRef, ...] = ()
    next_uid: int = 1

    def pattern(self, uid: int) -> Pattern:
        for pattern in self.patterns:
            if pattern.uid == uid:
                return pattern
        raise KeyError(f"no pattern with uid {uid}")

    def index_of(self, uid: int) -> int:
        for index, pattern in enumerate(self.patterns):
            if pattern.uid == uid:
                return index
        raise KeyError(f"no pattern with uid {uid}")

    def by_pattern_id(self, pattern_id: int) -> list[Pattern]:
        return [p for p in self.patterns if p.pattern_id == pattern_id]

    def pdf(self, pdf_id: int) -> PdfRef | None:
        return next((ref for ref in self.pdfs if ref.pdf_id == pdf_id), None)

    def with_pattern(self, pattern: Pattern) -> Project:
        """Replace the pattern with the same uid, keeping its list position."""
        index = self.index_of(pattern.uid)
        patterns = self.patterns[:index] + (pattern,) + self.patterns[index + 1:]
        return replace(self, patterns=patterns)
