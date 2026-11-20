"""Small builders for test patterns.

Positions are written the way an operator would snap them: as relations between
package edges, expressed with the symbols KL, KB and D.
"""

from fractions import Fraction

from layerforge.domain.linear import D, KB, KL, LinearForm, ZERO
from layerforge.domain.model import Dimensions, Package, Pattern

H = Fraction(1, 2)


def pkg(x: LinearForm, y: LinearForm, orientation: int = 0) -> Package:
    return Package(x, y, orientation)


def grid(columns: int, rows: int, orientation: int = 0, skip=()) -> tuple[Package, ...]:
    """Regular grid with gap D; `skip` holds (column, row) cells left empty."""
    w = KL if orientation == 0 else KB
    h = KB if orientation == 0 else KL
    out = []
    for r in range(rows):
        for c in range(columns):
            if (c, r) in skip:
                continue
            out.append(Package(w * H + (w + D) * c, h * H + (h + D) * r, orientation))
    return tuple(out)


def eu13() -> tuple[Package, ...]:
    """EU13 from Kave_Layerpattern.pdf: two lying packages stacked on the left, one
    standing package right of them, top-aligned with the upper one."""
    a = pkg(KL * H, KB * H)                                 # lower left
    b = pkg(KL * H, KB * Fraction(3, 2) + D)                # upper left
    c = pkg(KL + D + KB * H, KB * 2 + D - KL * H, 90)      # standing, top edge = 2KB + D
    return (a, b, c)


def pattern(packages, uid: int = 1, pattern_id: int = 1, dims: Dimensions | None = None,
            name: str | None = None) -> Pattern:
    """A pattern is only valid with a name; by default it is "P<PatternId>"."""
    return Pattern(uid, pattern_id, tuple(packages), dims or Dimensions(),
                   name=f"P{pattern_id}" if name is None else name)


def form(l=0, b=0, d=0) -> LinearForm:  # noqa: E741
    return LinearForm.of(l, b, d)


__all__ = ["D", "H", "KB", "KL", "ZERO", "eu13", "form", "grid", "pattern", "pkg"]
