"""Incremental project validation.

Patterns are immutable, so a pattern object that survived an edit unchanged still has
the same report. Only new pattern objects are checked again; the cross-pattern rules
(PatternId uniqueness, duplicates, mirrors) are cheap comparisons of cached keys.
An edit therefore costs one pattern check instead of a whole-project check.
"""

from __future__ import annotations

from layerforge.domain import validation as v
from layerforge.domain.duplicates import geometry_key, mirror_keys
from layerforge.domain.export_model import is_verified
from layerforge.domain.model import Pattern, Project

_UNUSABLE = (v.INVALID_DIMENSIONS, v.EMPTY, v.BAD_ORIENTATION, v.NOT_REPRESENTABLE)


class ProjectValidator:
    def __init__(self, max_packages: int) -> None:
        self.max_packages = max_packages
        # id(pattern) -> (pattern, local report, key, mirror keys); the pattern is kept
        # so its id cannot be reused by another object while the entry exists.
        self._cache: dict[int, tuple[Pattern, v.PatternReport, object, object]] = {}
        self._project: Project | None = None
        self._reports: dict[int, v.PatternReport] = {}

    def set_max_packages(self, value: int) -> None:
        if value != self.max_packages:
            self.max_packages = value
            self._cache.clear()
            self._project = None

    def _local(self, pattern: Pattern):
        entry = self._cache.get(id(pattern))
        if entry is None or entry[0] is not pattern:
            report = v.check_pattern(pattern, self.max_packages)
            usable = not any(report.has(code) for code in _UNUSABLE)
            entry = (pattern, report, geometry_key(pattern) if usable else None,
                     mirror_keys(pattern) if usable else None)
            self._cache[id(pattern)] = entry
        return entry

    def reports(self, project: Project) -> dict[int, v.PatternReport]:
        """uid -> report for every pattern; cached for the same project object."""
        if project is self._project:
            return self._reports
        entries = {p.uid: self._local(p) for p in project.patterns}
        live = {id(p) for p in project.patterns}
        for key in [k for k in self._cache if k not in live]:
            del self._cache[key]

        by_id: dict[int, list[int]] = {}
        by_key: dict[object, list[int]] = {}
        for p in project.patterns:
            by_id.setdefault(p.pattern_id, []).append(p.uid)
            key = entries[p.uid][2]
            if key is not None:
                by_key.setdefault(key, []).append(p.uid)
        ids = {p.uid: p.pattern_id for p in project.patterns}

        reports: dict[int, v.PatternReport] = {}
        for p in project.patterns:
            _pattern, local, key, mirrors = entries[p.uid]
            extra = []
            same_id = [u for u in by_id[p.pattern_id] if u != p.uid]
            if same_id:
                extra.append(v.Issue(v.DUPLICATE_ID, f"PatternId {p.pattern_id} is used more than "
                                                     f"once.", True, patterns=tuple(same_id)))
            twins = [u for u in by_key.get(key, []) if u != p.uid] if key is not None else []
            if twins:
                extra.append(v.Issue(v.DUPLICATE_GEOMETRY, "Identical geometry to pattern "
                                     + ", ".join(str(ids[u]) for u in twins) + ".", True,
                                     patterns=tuple(twins)))
            if mirrors is not None:
                similar = []
                for mk in mirrors:
                    for u in by_key.get(mk, []):
                        if u != p.uid and u not in twins and u not in similar:
                            similar.append(u)
                if similar:
                    extra.append(v.Issue(v.MIRROR_SIMILAR, "Mirror image of pattern "
                                         + ", ".join(str(ids[u]) for u in similar) + ".", False,
                                         patterns=tuple(similar)))
            reports[p.uid] = v.PatternReport(local.issues + tuple(extra), local.conditions) \
                if extra else local
        self._project, self._reports = project, reports
        return reports

    def export_blockers(self, project: Project) -> list[str]:
        """Why the project cannot be exported; empty = export allowed."""
        if not project.patterns:
            return ["The project contains no patterns."]
        reports = self.reports(project)
        out = []
        invalid = sorted(p.pattern_id for p in project.patterns if not reports[p.uid].valid)
        unverified = sorted(p.pattern_id for p in project.patterns
                            if reports[p.uid].valid and not is_verified(p))
        if invalid:
            out.append("Invalid patterns: " + ", ".join(map(str, invalid)) + ".")
        if unverified:
            out.append("Not verified: " + ", ".join(map(str, unverified)) + ".")
        return out
