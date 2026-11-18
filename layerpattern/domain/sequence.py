"""Placement sequence = order of the package tuple.

Because the order itself is the sequence, duplicate or missing sequence numbers
cannot occur, and moving a package never changes its number.
"""

from __future__ import annotations

from .geometry import units
from .model import Dimensions, Package


def auto_order(packages, dims: Dimensions) -> tuple[Package, ...]:
    """Reproducible initial order: rows from bottom to top, each row left to right.

    A row is the set of packages sharing the same bottom edge for the current
    example values; ties on both keys keep the previous order (stable sort).
    """
    return tuple(sorted(packages, key=lambda p: (units(p.bottom(), dims), units(p.left(), dims))))


def moved(packages, source: int, target: int) -> tuple[Package, ...]:
    """Move one package from index `source` to index `target` (list drag and drop)."""
    items = list(packages)
    items.insert(target, items.pop(source))
    return tuple(items)


def reordered(packages, order) -> tuple[Package, ...]:
    """`order` lists the old indexes in the new sequence; it must be a permutation."""
    order = list(order)
    if sorted(order) != list(range(len(packages))):
        raise ValueError("order must contain every package exactly once")
    return tuple(packages[i] for i in order)
