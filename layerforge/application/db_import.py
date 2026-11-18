"""A generated DB as the starting point of a new project."""

from __future__ import annotations

from layerforge.domain.geometry import normalized
from layerforge.domain.model import Dimensions, Origin, Package, Pattern, Project
from layerforge.infrastructure.tia_import import ImportedDb


def project_from_db(imported: ImportedDb, dims: Dimensions, name: str = "") -> Project:
    """Rebuild displayable patterns from the coefficients, all unverified.

    The coefficients are positions relative to the pattern centre, so they can be
    used as positions directly. If `dims` lie in a different validity range than the
    exported data, the reconstructed pattern will show it (conditions, overlaps).
    """
    patterns = []
    for uid, item in enumerate(imported.patterns, start=1):
        packages = normalized([Package(x, y, o) for o, x, y in item.packages], dims)
        patterns.append(Pattern(uid, item.pattern_id, packages, dims, None, None, Origin.DB_IMPORT))
    return Project(name or imported.project_name or "Imported", tuple(patterns), (),
                   len(patterns) + 1)
