"""Recognised rectangles -> symbolic pattern (decision D15).

PDF layer drawings are schematic: the same case may be drawn 53 x 68 px standing and
80 x 45 px lying in one pattern. Millimetre-like normalisation is therefore useless.
Instead the drawing is read as topology:

* orientation of each package from its own aspect ratio (wider than high = 0),
* relations between packages from drawing evidence: touching or a small gap means
  "adjacent with one D", equal edges mean "flush", equal centres "centred", a centre
  on an edge "half step",
* positions are derived along those relations, separately for X and Y, starting at
  the lower-left package and always preferring the strongest evidence.

Only the strength of the evidence uses tolerances; the result is exact.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from statistics import median

from .geometry import normalized, primitive, units
from .linear import D, KB, KL, LinearForm
from .model import Dimensions, Package
from .sequence import auto_order

# Relation strength, lower = preferred.
ADJACENT, FLUSH, CENTRED, HALF_STEP, ESTIMATED = range(5)

DrawnRect = tuple[float, float, float, float]   # x0, y0, x1, y1 with Y pointing up


@dataclass(frozen=True, slots=True)
class Tolerances:
    """Relative to the median short side of the drawn packages."""

    edge: float = 0.06          # edges/centres closer than this are "equal"
    gap: float = 0.35           # a free gap up to this is still "adjacent"
    size: float = 0.10          # allowed size deviation from the cluster
    square: float = 0.05        # |w - h| below this: orientation not readable
    min_edge_px: float = 1.0    # absolute floor for tiny drawings
    min_gap_px: float = 2.0


@dataclass(frozen=True, slots=True)
class Reconstruction:
    packages: tuple[Package, ...]        # normalised, automatic placement sequence
    source_index: tuple[int, ...]        # input rectangle of each package
    uncertain: tuple[int, ...]           # package indexes with weak evidence (yellow)
    estimated: tuple[int, ...]           # positions without any drawing evidence (red)
    messages: tuple[str, ...]
    hints: tuple[LinearForm, ...] = ()   # drawn intent, e.g. 3*KL - 4*KB = 0 (see drawing_hints)


@dataclass(frozen=True, slots=True)
class _Axis:
    lo: list[float]         # drawn lower edge per package on this axis
    hi: list[float]
    other_lo: list[float]   # the perpendicular interval, for "facing"
    other_hi: list[float]
    half: list[LinearForm]  # symbolic half size on this axis


def _relations(axis: _Axis, tol: float, gap_max: float):
    """All (strength, error, source, target, offset) where target = source + offset."""
    n = len(axis.lo)
    out = []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            lo_i, hi_i, lo_j, hi_j = axis.lo[i], axis.hi[i], axis.lo[j], axis.hi[j]
            c_i, c_j = (lo_i + hi_i) / 2, (lo_j + hi_j) / 2
            h_i, h_j = axis.half[i], axis.half[j]
            facing = (min(axis.other_hi[i], axis.other_hi[j])
                      - max(axis.other_lo[i], axis.other_lo[j])) > tol
            if facing:
                after = lo_j - hi_i
                if -tol <= after <= gap_max:
                    out.append((ADJACENT, 0.0, i, j, h_i + D + h_j))
                before = lo_i - hi_j
                if -tol <= before <= gap_max:
                    out.append((ADJACENT, 0.0, i, j, -(h_i + D + h_j)))
            for strength, error, offset in (
                (FLUSH, abs(lo_i - lo_j), h_j - h_i),
                (FLUSH, abs(hi_i - hi_j), h_i - h_j),
                (CENTRED, abs(c_i - c_j), LinearForm()),
                (HALF_STEP, abs(c_j - lo_i), -h_i),
                (HALF_STEP, abs(c_j - hi_i), h_i),
                (HALF_STEP, abs(lo_j - c_i), h_j),
                (HALF_STEP, abs(hi_j - c_i), -h_j),
            ):
                if error <= tol:
                    out.append((strength, error, i, j, offset))
    return out


def _solve(axis: _Axis, tol: float, gap_max: float, dims: Dimensions,
           anchor: int) -> tuple[list[LinearForm], set[int]]:
    """Best-first propagation from `anchor`; returns positions and estimated indexes."""
    n = len(axis.lo)
    relations = _relations(axis, tol, gap_max)
    by_source: dict[int, list] = {}
    for rel in relations:
        by_source.setdefault(rel[2], []).append(rel)

    pos: list[LinearForm | None] = [None] * n
    estimated: set[int] = set()
    heap: list = []
    counter = 0

    def place(k: int, value: LinearForm) -> None:
        nonlocal counter
        pos[k] = value
        for strength, error, _i, j, offset in by_source.get(k, []):
            if pos[j] is None:
                heapq.heappush(heap, (strength, error, counter, k, j, offset))
                counter += 1

    place(anchor, axis.half[anchor])            # lower edge of the anchor at 0
    while any(p is None for p in pos):
        while heap:
            strength, _error, _c, i, j, offset = heapq.heappop(heap)
            if pos[j] is not None:
                continue
            value = pos[i] + offset
            if strength == ADJACENT:
                # Several placed neighbours on the same side: take the one that pushes
                # the package furthest away, so it overlaps none of them.
                sign = 1 if units(offset, dims) > 0 else -1
                for s2, _e2, i2, j2, off2 in relations:
                    if j2 == j and s2 == ADJACENT and pos[i2] is not None:
                        cand = pos[i2] + off2
                        if (units(off2, dims) > 0) == (sign > 0) and \
                                sign * units(cand, dims) > sign * units(value, dims):
                            value = cand
            place(j, value)
        if all(p is not None for p in pos):
            break
        # No evidence links the rest: attach the nearest unplaced package to its
        # nearest placed one as an adjacent neighbour and flag it.
        best = None
        for j in (k for k in range(n) if pos[k] is None):
            for i in (k for k in range(n) if pos[k] is not None):
                c_i = (axis.lo[i] + axis.hi[i]) / 2
                c_j = (axis.lo[j] + axis.hi[j]) / 2
                dist = abs(c_j - c_i)
                if best is None or dist < best[0]:
                    best = (dist, i, j, 1 if c_j >= c_i else -1)
        _dist, i, j, sign = best
        estimated.add(j)
        place(j, pos[i] + (axis.half[i] + D + axis.half[j]) * sign)
    return pos, estimated  # type: ignore[return-value]


def reconstruct(drawn: list[DrawnRect], dims: Dimensions,
                tolerances: Tolerances = Tolerances()) -> Reconstruction:
    if not drawn:
        return Reconstruction((), (), (), (), ("No packages.",))
    widths = [x1 - x0 for x0, _y0, x1, _y1 in drawn]
    heights = [y1 - y0 for _x0, y0, _x1, y1 in drawn]
    longs = [max(w, h) for w, h in zip(widths, heights)]
    shorts = [min(w, h) for w, h in zip(widths, heights)]
    long_med, short_med = median(longs), median(shorts)
    tol = max(tolerances.min_edge_px, tolerances.edge * short_med)
    gap_max = max(tolerances.min_gap_px, tolerances.gap * short_med)

    orientation = [0 if w >= h else 90 for w, h in zip(widths, heights)]
    uncertain: set[int] = set()
    messages: list[str] = []
    for k, (w, h) in enumerate(zip(widths, heights)):
        if abs(w - h) <= tolerances.square * max(w, h):
            uncertain.add(k)
        if abs(longs[k] - long_med) > tolerances.size * long_med or \
                abs(shorts[k] - short_med) > tolerances.size * short_med:
            uncertain.add(k)
    if uncertain:
        messages.append("Some packages differ in drawn size or shape; check orientation and position.")

    half_x = [(KL if o == 0 else KB).half() for o in orientation]
    half_y = [(KB if o == 0 else KL).half() for o in orientation]
    x0s = [r[0] for r in drawn]
    x1s = [r[2] for r in drawn]
    y0s = [r[1] for r in drawn]
    y1s = [r[3] for r in drawn]

    def anchor(primary: list[float], secondary: list[float]) -> int:
        return min(range(len(drawn)), key=lambda k: (primary[k], secondary[k]))

    xs, est_x = _solve(_Axis(x0s, x1s, y0s, y1s, half_x), tol, gap_max, dims, anchor(x0s, y0s))
    ys, est_y = _solve(_Axis(y0s, y1s, x0s, x1s, half_y), tol, gap_max, dims, anchor(y0s, x0s))
    estimated = est_x | est_y
    if estimated:
        messages.append("Some positions could not be derived from the drawing and were estimated.")

    placed = [Package(x, y, o) for x, y, o in zip(xs, ys, orientation)]
    hints = drawing_hints(drawn, placed, tol)
    packages = normalized(placed, dims)
    ordered = auto_order(packages, dims)
    # Map every ordered package back to its input rectangle (identity, not equality:
    # two rectangles can never yield the same package without overlapping).
    remaining = list(range(len(packages)))
    source_index = []
    for p in ordered:
        k = next(k for k in remaining if packages[k] is p)
        remaining.remove(k)
        source_index.append(k)
    back = {src: new for new, src in enumerate(source_index)}
    return Reconstruction(
        ordered, tuple(source_index),
        tuple(sorted(back[k] for k in uncertain)), tuple(sorted(back[k] for k in estimated)),
        tuple(messages), hints,
    )


def drawing_hints(drawn: list[DrawnRect], packages: list[Package], tol: float) -> tuple[LinearForm, ...]:
    """What the drawing says about the package proportions.

    Two edges that are flush in the drawing but were placed through different
    relations stay apart for most KL/KB - unless the case was designed so that they
    meet (e.g. four standing cases as wide as three lying ones: 3*KL = 4*KB).
    Each such pair yields one equation in KL and KB. The D part is dropped: a
    schematic drawing does not show where the safety gaps go.
    """
    found: set[LinearForm] = set()
    sides = (
        (lambda r: r[0], Package.left), (lambda r: r[2], Package.right),
        (lambda r: r[1], Package.bottom), (lambda r: r[3], Package.top),
    )
    for drawn_edge, symbolic_edge in sides:
        for i in range(len(packages)):
            for j in range(i + 1, len(packages)):
                if abs(drawn_edge(drawn[i]) - drawn_edge(drawn[j])) > tol:
                    continue
                diff = symbolic_edge(packages[i]) - symbolic_edge(packages[j])
                ratio = LinearForm(diff.l, diff.b)
                if not ratio.is_zero():
                    found.add(primitive(ratio, positive=True))
    return tuple(sorted(found, key=LinearForm.complexity))


def flip_y(rects: list[DrawnRect], page_height: float) -> list[DrawnRect]:
    """Page coordinates (Y down) to drawing coordinates (Y up)."""
    return [(x0, page_height - y1, x1, page_height - y0) for x0, y0, x1, y1 in rects]
