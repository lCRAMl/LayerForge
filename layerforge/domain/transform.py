"""Whole-pattern rotation by multiples of 90 degrees (counter-clockwise)."""

from __future__ import annotations

from dataclasses import replace

from .geometry import normalized
from .model import Dimensions, Package


def rotate_packages(packages, quarter_turns: int, dims: Dimensions) -> tuple[Package, ...]:
    """Rotate about the pattern centre; the package order is kept.

    A quarter turn maps (x, y) to (-y, x) and swaps the orientation. Rotating about
    the origin and renormalising is the same as rotating about the centre, because
    the bounding box rotates with the pattern.
    """
    turns = quarter_turns % 4
    out = []
    for p in packages:
        x, y = p.x, p.y
        for _ in range(turns):
            x, y = -y, x
        orientation = p.orientation if turns % 2 == 0 else (90 if p.orientation == 0 else 0)
        out.append(replace(p, x=x, y=y, orientation=orientation))
    return normalized(out, dims)
