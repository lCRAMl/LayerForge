"""Automatic package order.

The order of the packages inside a pattern carries no meaning: the PLC computes the
placement order from where the pallet stands relative to the pickup point. The export
still needs *some* reproducible order, and a readable one helps when someone looks at
the DB: rows from bottom to top, each row left to right.
"""

from __future__ import annotations

from .geometry import units
from .model import Dimensions, Package


def auto_order(packages, dims: Dimensions) -> tuple[Package, ...]:
    """Rows from bottom to top, each row left to right.

    A row is the set of packages sharing the same bottom edge for the current
    example values; ties on both keys keep the previous order (stable sort).
    """
    return tuple(sorted(packages, key=lambda p: (units(p.bottom(), dims), units(p.left(), dims))))
