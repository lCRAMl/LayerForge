"""Symbolic snapping (decisions D13, D14).

A package position is never free: on each axis it is one relation to a reference
package, written exactly in KL, KB and D. The editor asks for all candidate relations
once when a drag starts, compares their millimetre values with the cursor while
dragging, and commits the chosen exact form on release.

Catalogue per axis (strongest first):
  ADJACENT  - next to the reference with exactly one D in between
  FLUSH     - lower or upper edges aligned
  CENTRED   - centres aligned
  HALF_STEP - centre on an edge of the reference, or an edge on its centre
"""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import mm, units
from .linear import D, KB, KL, LinearForm, ZERO
from .model import Dimensions, Package

ADJACENT, FLUSH, CENTRED, HALF_STEP = range(4)

_NAMES = {
    "x": {"after": "right of", "before": "left of", "lo": "left edges flush with",
          "hi": "right edges flush with", "centre": "centred on", "on_lo": "centre on left edge of",
          "on_hi": "centre on right edge of", "lo_on": "left edge on centre of",
          "hi_on": "right edge on centre of"},
    "y": {"after": "above", "before": "below", "lo": "bottom edges flush with",
          "hi": "top edges flush with", "centre": "centred on", "on_lo": "centre on bottom edge of",
          "on_hi": "centre on top edge of", "lo_on": "bottom edge on centre of",
          "hi_on": "top edge on centre of"},
}


@dataclass(frozen=True, slots=True)
class Candidate:
    value: LinearForm      # centre coordinate of the moving package on this axis
    strength: int
    reference: int         # index of the reference package in the pattern
    text: str              # e.g. "right of #3"
    mm: float              # value for the current example values, for fast comparison
    feature: str = "c"     # which part of the mover is aligned: "lo" edge, "hi" edge, "c" centre


def half_size(orientation: int, axis: str) -> LinearForm:
    along_x = KL if orientation == 0 else KB
    along_y = KB if orientation == 0 else KL
    return (along_x if axis == "x" else along_y).half()


def axis_candidates(axis: str, mover_orientation: int, references, dims: Dimensions) -> list[Candidate]:
    """All relations of a package with `mover_orientation` to each (index, Package) reference."""
    hm = half_size(mover_orientation, axis)
    names = _NAMES[axis]
    seen: dict[LinearForm, Candidate] = {}
    for index, ref in references:
        c = ref.x if axis == "x" else ref.y
        hr = half_size(ref.orientation, axis)
        tag = f"#{index + 1}"
        for strength, value, key, feature in (
            (ADJACENT, c + hr + D + hm, "after", "lo"),
            (ADJACENT, c - hr - D - hm, "before", "hi"),
            (FLUSH, c - hr + hm, "lo", "lo"),
            (FLUSH, c + hr - hm, "hi", "hi"),
            (CENTRED, c, "centre", "c"),
            (HALF_STEP, c - hr, "on_lo", "c"),
            (HALF_STEP, c + hr, "on_hi", "c"),
            (HALF_STEP, c + hm, "lo_on", "lo"),
            (HALF_STEP, c - hm, "hi_on", "hi"),
        ):
            cand = Candidate(value, strength, index, f"{names[key]} {tag}",
                             float(mm(units(value, dims))), feature)
            # Equal forms from different relations (e.g. flush = centred for equal
            # sizes): keep the strongest, then the first reference.
            old = seen.get(value)
            if old is None or (strength, index) < (old.strength, old.reference):
                seen[value] = cand
    return list(seen.values())


def _rank(c: Candidate) -> tuple:
    return (c.strength, c.value.complexity(), c.reference)


def resolve(candidates: list[Candidate], target_mm: float, radius_mm: float | None,
            tie_mm: float = 0.5) -> Candidate | None:
    """Best candidate near `target_mm`.

    Within `radius_mm` (None = unlimited) the nearest wins; candidates that render
    within `tie_mm` of it are treated as the same spot, and the simplest relation is
    preferred there.
    """
    if not candidates:
        return None
    best = min(abs(c.mm - target_mm) for c in candidates)
    if radius_mm is not None and best > radius_mm:
        return None
    close = [c for c in candidates if abs(c.mm - target_mm) <= best + tie_mm]
    return min(close, key=_rank)


def first_package_position(orientation: int) -> tuple[LinearForm, LinearForm]:
    """In an empty pattern the first package sits with its lower-left corner at the origin."""
    return half_size(orientation, "x"), half_size(orientation, "y")


def snap_package(packages, index: int | None, orientation: int, target: tuple[float, float],
                 dims: Dimensions, exclude=()) -> tuple[Package, Candidate | None, Candidate | None]:
    """Exact package closest to `target` (centre in mm), relative to all other packages.

    `index` is the moving package (excluded as reference), `exclude` further indexes
    (the rest of a moved group). Used on release, after rotation (D14) and when
    placing new packages.
    """
    refs = [(i, p) for i, p in enumerate(packages) if i != index and i not in exclude]
    if not refs:
        x, y = first_package_position(orientation)
        return Package(x, y, orientation), None, None
    cx = resolve(axis_candidates("x", orientation, refs, dims), target[0], None)
    cy = resolve(axis_candidates("y", orientation, refs, dims), target[1], None)
    return Package(cx.value if cx else ZERO, cy.value if cy else ZERO, orientation), cx, cy
