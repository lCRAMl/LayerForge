"""Fit to pallet: suggest KL and KB on a round grid for a fixed pattern.

The arrangement never changes - only the case size is searched. Rule (agreed with the
user, see PROGRESS.md "Fit to pallet"):

1. The pattern stays as drawn: every drawing hint (an equation in KL and KB, e.g.
   3*KL - 4*KB = 0) holds within one grid step.
2. Candidates: KL >= KB, multiples of the grid step, pattern valid for them.
3. Fit deviation in mm = 2 x overhang + unused pallet edge, width plus length.
4. Of all candidates at most `band` mm worse than the best fit, the "roundest" wins
   (multiple of 100 > 50 > 10, KL and KB added); then less overhang, then more area.

D and the pallet are given; they are machine and pallet data, not a design choice.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd

from . import validation
from .cancel import Cancelled
from .geometry import UNIT, primitive
from .linear import LinearForm
from .model import Dimensions, Package, Pattern

MIN_SIDE = 50            # smaller cases are not palletised; also bounds the search
SEARCH_FACTOR = 1.3      # candidates may overhang, but not grotesquely
ROUND_LEVELS = ((100, 3), (50, 2), (10, 1))


def roundness(value: int) -> int:
    return next((score for step, score in ROUND_LEVELS if value % step == 0), 0)


@dataclass(frozen=True, slots=True)
class FitResult:
    kl: int
    kb: int
    width: float              # pattern outline in mm
    height: float
    overhang_x: float         # per side, mm (0 if inside)
    overhang_y: float
    area: float               # package footprint / pallet area
    deviation: float          # rule step 3, mm
    drawing_kept: bool        # False if the hints could not be met and were ignored

    def summary(self) -> str:
        over = ""
        if self.overhang_x or self.overhang_y:
            over = f", overhang {self.overhang_x:g} / {self.overhang_y:g} mm per side"
        return (f"KL {self.kl} x KB {self.kb}: pattern {self.width:g} x {self.height:g} mm, "
                f"{self.area:.0%} of the pallet{over}")


def _ints(form: LinearForm) -> tuple[int, int, int]:
    return tuple(int(c * UNIT) for c in form.coefficients())


def _edges(packages) -> tuple[list, list, list, list]:
    """Distinct edge forms per side as integer coefficients in 1/UNIT mm."""
    return tuple(sorted({_ints(edge(p)) for p in packages}) for edge in
                 (Package.left, Package.right, Package.bottom, Package.top))


def applicable_hints(packages, hints) -> list[tuple[int, int]]:
    """Hints that still describe two edges of the current pattern, as coprime (a, b).

    After editing, a hint may refer to edges that no longer exist; it is then ignored
    instead of forcing a proportion the pattern does not need any more.
    """
    if not hints:
        return []
    present: set[LinearForm] = set()
    for side in (Package.left, Package.right, Package.bottom, Package.top):
        forms = list({side(p) for p in packages})
        for i, a in enumerate(forms):
            for b in forms[i + 1:]:
                diff = a - b
                ratio = LinearForm(diff.l, diff.b)
                if not ratio.is_zero():
                    present.add(primitive(ratio, positive=True))
    out = []
    for hint in hints:
        key = primitive(LinearForm(hint.l, hint.b), positive=True)
        if key in present:
            a, b = int(key.l), int(key.b)
            common = gcd(a, b) or 1
            out.append((a // common, b // common))
    return out


def _span(forms_lo, forms_hi, kl: int, kb: int, d: int) -> int:
    lo = min(a * kl + b * kb + c * d for a, b, c in forms_lo)
    hi = max(a * kl + b * kb + c * d for a, b, c in forms_hi)
    return hi - lo


def _search(packages, ratios, pallet_x: int, pallet_y: int, d: int, step: int, cancel):
    lefts, rights, bottoms, tops = _edges(packages)
    count = len(packages)
    start = -(-MIN_SIDE // step) * step
    limit = int(SEARCH_FACTOR * max(pallet_x, pallet_y))
    px, py = pallet_x * UNIT, pallet_y * UNIT
    found = []
    for kb in range(start, limit + 1, step):
        if cancel is not None and cancel():
            raise Cancelled()
        for kl in range(kb, limit + 1, step):
            if any(abs(a * kl + b * kb) > step for a, b in ratios):
                continue
            w = _span(lefts, rights, kl, kb, d)
            h = _span(bottoms, tops, kl, kb, d)
            if w > SEARCH_FACTOR * px and h > SEARCH_FACTOR * py:
                break                         # larger KL only grows the pattern further
            dx, dy = (w - px) / UNIT, (h - py) / UNIT
            deviation = (2 * dx if dx > 0 else -dx) + (2 * dy if dy > 0 else -dy)
            found.append((deviation, kl, kb, w / UNIT, h / UNIT, max(dx, 0.0), max(dy, 0.0),
                          count * kl * kb / (pallet_x * pallet_y)))
    return found


def fit_to_pallet(packages, hints, pallet_x: int, pallet_y: int, d: int, step: int = 10,
                  band: float = 25.0, count: int = 3, cancel=None) -> list[FitResult]:
    """The `count` best KL/KB suggestions, best first; empty if nothing valid exists."""
    packages = tuple(packages)
    if not packages or pallet_x <= 0 or pallet_y <= 0 or d < 0 or step <= 0:
        return []
    ratios = applicable_hints(packages, hints)
    kept = True
    found = _search(packages, ratios, pallet_x, pallet_y, d, step, cancel)
    if not found and ratios:
        kept = False                          # the drawing's proportions are unreachable
        found = _search(packages, [], pallet_x, pallet_y, d, step, cancel)
    if not found:
        return []
    best = min(f[0] for f in found)
    pool = [f for f in found if f[0] <= best + band]
    pool.sort(key=lambda f: (-(roundness(f[1]) + roundness(f[2])), f[5] + f[6], -f[7], f[0]))
    results: list[FitResult] = []
    for deviation, kl, kb, w, h, ox, oy, area in pool:
        dims = Dimensions(kl, kb, d, pallet_x, pallet_y)
        # The package-count limit is a project rule, not a question of size.
        if not validation.check_pattern(Pattern(0, 1, packages, dims), len(packages), require_name=False).valid:
            continue
        results.append(FitResult(kl, kb, w, h, ox / 2, oy / 2, area, deviation, kept))
        if len(results) == count:
            break
    return results
