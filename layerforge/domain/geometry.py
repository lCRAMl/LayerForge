"""Geometry of one pattern for its current example values.

Evaluation is exact: forms are turned into integers in units of 1/`UNIT` mm. With
whole-millimetre KL/KB/D and coefficients of at most 1/16 this is lossless, so
"touching", "gap equals D" and "overlap" are decided without any tolerance.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations

from .linear import LinearForm
from .model import Dimensions, Package

UNIT = 16


def units(form: LinearForm, dims: Dimensions) -> int:
    value = form.value(dims.kl, dims.kb, dims.d) * UNIT
    if value.denominator != 1:
        # Only reachable with coefficients outside the 1/16 policy.
        raise ValueError(f"{form} cannot be evaluated exactly")
    return value.numerator


def mm(value_units: int) -> Fraction:
    return Fraction(value_units, UNIT)


@dataclass(frozen=True, slots=True)
class Rect:
    x0: int
    y0: int
    x1: int
    y1: int


def rects(packages, dims: Dimensions) -> list[Rect]:
    return [Rect(units(p.left(), dims), units(p.bottom(), dims),
                 units(p.right(), dims), units(p.top(), dims)) for p in packages]


def _overlap(a0: int, a1: int, b0: int, b1: int) -> int:
    """Length of the common part of two intervals; negative means a gap."""
    return min(a1, b1) - max(a0, b0)


def overlapping_pairs(boxes: list[Rect]) -> list[tuple[int, int]]:
    return [(i, j) for (i, a), (j, b) in combinations(enumerate(boxes), 2)
            if _overlap(a.x0, a.x1, b.x0, b.x1) > 0 and _overlap(a.y0, a.y1, b.y0, b.y1) > 0]


def facing_gaps(boxes: list[Rect]):
    """(i, j, gap) for pairs that face each other across a free gap.

    Facing means the projections onto the other axis overlap by a positive length;
    packages that only meet at a corner (diagonal contact) never face each other.
    """
    for (i, a), (j, b) in combinations(enumerate(boxes), 2):
        over_x = _overlap(a.x0, a.x1, b.x0, b.x1)
        over_y = _overlap(a.y0, a.y1, b.y0, b.y1)
        if over_y > 0 and over_x <= 0:
            yield i, j, -over_x
        elif over_x > 0 and over_y <= 0:
            yield i, j, -over_y


def neighbour_pairs(boxes: list[Rect], dims: Dimensions) -> list[tuple[int, int]]:
    gap = dims.d * UNIT
    return [(i, j) for i, j, g in facing_gaps(boxes) if g == gap]


def clearance_pairs(boxes: list[Rect], dims: Dimensions) -> list[tuple[int, int]]:
    """Facing pairs closer than the safety gap D (decision D12)."""
    gap = dims.d * UNIT
    return [(i, j) for i, j, g in facing_gaps(boxes) if g < gap]


def components(count: int, pairs) -> list[list[int]]:
    parent = list(range(count))

    def root(k: int) -> int:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for i, j in pairs:
        parent[root(i)] = root(j)
    groups: dict[int, list[int]] = {}
    for k in range(count):
        groups.setdefault(root(k), []).append(k)
    return sorted(groups.values())


# --- bounding box ------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Extent:
    """Symbolic bounding box: for each side the package edge that is extreme for
    the current example values (ties: the simplest form)."""

    left: LinearForm
    right: LinearForm
    bottom: LinearForm
    top: LinearForm
    # all candidate edges per side, needed for the validity conditions
    lefts: tuple[LinearForm, ...] = ()
    rights: tuple[LinearForm, ...] = ()
    bottoms: tuple[LinearForm, ...] = ()
    tops: tuple[LinearForm, ...] = ()

    def center(self) -> tuple[LinearForm, LinearForm]:
        return (self.left + self.right).half(), (self.bottom + self.top).half()

    def width(self) -> LinearForm:
        return self.right - self.left

    def height(self) -> LinearForm:
        return self.top - self.bottom


def _extreme(forms: list[LinearForm], dims: Dimensions, largest: bool) -> LinearForm:
    values = [units(f, dims) for f in forms]
    best = max(values) if largest else min(values)
    return min((f for f, v in zip(forms, values) if v == best), key=LinearForm.complexity)


def extent(packages, dims: Dimensions) -> Extent:
    if not packages:
        raise ValueError("an empty pattern has no extent")
    lefts = [p.left() for p in packages]
    rights = [p.right() for p in packages]
    bottoms = [p.bottom() for p in packages]
    tops = [p.top() for p in packages]
    return Extent(_extreme(lefts, dims, False), _extreme(rights, dims, True),
                  _extreme(bottoms, dims, False), _extreme(tops, dims, True),
                  tuple(set(lefts)), tuple(set(rights)), tuple(set(bottoms)), tuple(set(tops)))


def corner_relative(packages, dims: Dimensions) -> list[tuple[LinearForm, LinearForm]]:
    """Package centres relative to the lower-left bounding-box corner: the exported geometry."""
    box = extent(packages, dims)
    return [(p.x - box.left, p.y - box.bottom) for p in packages]


def centre_relative(packages, dims: Dimensions) -> list[tuple[LinearForm, LinearForm]]:
    """Package centres relative to the bounding-box centre (symmetric frame for mirroring)."""
    cx, cy = extent(packages, dims).center()
    return [(p.x - cx, p.y - cy) for p in packages]


def normalized(packages, dims: Dimensions) -> tuple[Package, ...]:
    """Move the origin to the lower-left corner of the bounding box.

    Purely cosmetic for storage (non-negative, readable coordinates) but it also keeps
    denominators small: shifting by an edge never halves anything.
    """
    if not packages:
        return ()
    box = extent(packages, dims)
    return tuple(p.moved(-box.left, -box.bottom) for p in packages)


# --- validity conditions (decision D11) ------------------------------------

def holds_for_all(form: LinearForm) -> bool:
    """True if form >= 0 for every KL >= KB > 0 and D >= 0.

    With KL = KB + t (t >= 0) the form reads (l+b)*KB + l*t + d*D, which is
    non-negative for all admissible values exactly when all three factors are.
    """
    return form.l + form.b >= 0 and form.l >= 0 and form.d >= 0


def primitive(form: LinearForm, positive: bool = False) -> LinearForm:
    """Scale to coprime integer coefficients so equivalent relations compare equal.

    `positive` also fixes the sign (first non-zero coefficient > 0) - for equations,
    where f = 0 and -f = 0 say the same; not for inequalities.
    """
    from math import gcd, lcm
    coeffs = form.coefficients()
    scale = lcm(*(c.denominator for c in coeffs))
    ints = [int(c * scale) for c in coeffs]
    common = gcd(*ints) or 1
    if positive and next((i for i in ints if i), 0) < 0:
        common = -common
    return LinearForm.of(*(Fraction(i, common) for i in ints))


@dataclass(frozen=True, slots=True)
class Condition:
    """The exported coefficients stay correct while `form >= 0` holds."""

    form: LinearForm

    def text(self, times: str = "·", ge: str = "≥") -> str:
        positive = LinearForm.of(*(max(c, 0) for c in self.form.coefficients()))
        negative = LinearForm.of(*(max(-c, 0) for c in self.form.coefficients()))
        return f"{positive.text(times)} {ge} {negative.text(times)}"


def validity_conditions(packages, dims: Dimensions) -> list[Condition]:
    """Inequalities under which the left and bottom outline edges stay the extreme ones.

    The coefficients are measured from the lower-left corner, so only those two edges
    matter. Outside the conditions another package defines that corner and every
    exported coefficient would be different. The right and top edges are irrelevant:
    the PLC computes the outline from the packages itself.
    """
    if not packages:
        return []
    box = extent(packages, dims)
    seen: set[LinearForm] = set()
    out: list[Condition] = []

    def need(form: LinearForm) -> None:
        if form.is_zero() or holds_for_all(form):
            return
        key = primitive(form)
        if key not in seen:
            seen.add(key)
            out.append(Condition(key))

    for other in box.lefts:
        need(other - box.left)
    for other in box.bottoms:
        need(other - box.bottom)
    return out


def overhang(packages, dims: Dimensions) -> tuple[Fraction, Fraction]:
    """Overhang per side in mm (X, Y) of the centred pattern beyond the pallet; 0 if none."""
    if not packages:
        return Fraction(0), Fraction(0)
    box = extent(packages, dims)
    width = mm(units(box.width(), dims))
    height = mm(units(box.height(), dims))
    return max(Fraction(0), (width - dims.pallet_x) / 2), max(Fraction(0), (height - dims.pallet_y) / 2)
