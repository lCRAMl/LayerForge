"""Exact duplicates and mirrored similarities between patterns.

Both compare what is exported: the multiset of (BaseOrientation, coefficients)
relative to the pattern centre. That is translation-independent by construction and
ignores the placement sequence. A globally rotated pattern differs (other
coefficients, swapped orientations) and is therefore a separate pattern.
"""

from __future__ import annotations

from .export_model import package_rows
from .model import Pattern

Key = tuple


def _key(rows) -> Key:
    return tuple(sorted((o, x.coefficients(), y.coefficients()) for o, x, y in rows))


def geometry_key(pattern: Pattern) -> Key | None:
    if not pattern.packages or not pattern.dims.is_valid():
        return None
    return _key(package_rows(pattern))


def mirror_keys(pattern: Pattern) -> tuple[Key, Key] | None:
    """Keys of the pattern mirrored left-right (x -> -x) and top-bottom (y -> -y)."""
    if not pattern.packages or not pattern.dims.is_valid():
        return None
    rows = package_rows(pattern)
    return (_key((o, -x, y) for o, x, y in rows), _key((o, x, -y) for o, x, y in rows))


def compare(patterns) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """(duplicates, similar): uid -> uids of the other patterns concerned."""
    keys = {p.uid: geometry_key(p) for p in patterns}
    duplicates: dict[int, list[int]] = {}
    by_key: dict[Key, list[int]] = {}
    for uid, key in keys.items():
        if key is not None:
            by_key.setdefault(key, []).append(uid)
    for uids in by_key.values():
        for uid in uids:
            others = [u for u in uids if u != uid]
            if others:
                duplicates[uid] = others

    similar: dict[int, list[int]] = {}
    for pattern in patterns:
        mirrored = mirror_keys(pattern)
        if mirrored is None:
            continue
        hits = []
        for key in mirrored:
            for uid in by_key.get(key, []):
                # A symmetric pattern mirrors onto itself; exact duplicates are
                # reported as such, not again as "similar".
                if uid != pattern.uid and uid not in duplicates.get(pattern.uid, []) and uid not in hits:
                    hits.append(uid)
        if hits:
            similar[pattern.uid] = hits
    return duplicates, similar
