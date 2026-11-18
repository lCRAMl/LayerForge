"""Project file: versioned JSON, extension `.layerforge.json` (decision D21).

Files of the former name (`.layerpattern.json`, format "layerpattern-project") still open.

Coefficients are stored as exact fraction strings ("1/2"), so a round trip never
changes the geometry. The pattern array order is the manual list order; the package
array order is the placement sequence.
"""

from __future__ import annotations

import json
import os
import tempfile
from fractions import Fraction
from pathlib import Path

from layerforge import APP_NAME, APP_VERSION
from layerforge.domain import rational
from layerforge.domain.linear import LinearForm
from layerforge.domain.model import (
    ORIENTATIONS, Dimensions, Origin, Package, Pattern, PdfRef, Project, SourceRef
)

EXTENSION = ".layerforge.json"
LEGACY_EXTENSIONS = (".layerpattern.json",)
FORMAT = "layerforge-project"
ACCEPTED_FORMATS = (FORMAT, "layerpattern-project")
SCHEMA_VERSION = 1


class ProjectFileError(Exception):
    """The file cannot be read as a project; the message is meant for the user."""


# --- writing -----------------------------------------------------------------

def _form(f: LinearForm) -> list[str]:
    return [str(c) for c in f.coefficients()]


def to_dict(project: Project) -> dict:
    return {
        "format": FORMAT,
        "schemaVersion": SCHEMA_VERSION,
        "generator": f"{APP_NAME} {APP_VERSION}",
        "name": project.name,
        "settings": {},
        "pdfs": [{"id": ref.pdf_id, "path": ref.path} for ref in project.pdfs],
        "patterns": [{
            "patternId": p.pattern_id,
            "origin": p.origin,
            "verified": p.verified,
            "dimensions": {"KL": p.dims.kl, "KB": p.dims.kb, "D": p.dims.d,
                           "palletWidth": p.dims.pallet_x, "palletLength": p.dims.pallet_y},
            "source": None if p.source is None else {
                "pdf": p.source.pdf_id, "page": p.source.page, "rect": list(p.source.rect)},
            "packages": [{"orientation": k.orientation, "x": _form(k.x), "y": _form(k.y)}
                         for k in p.packages],
            # Optional (schema 1 readers ignore it): KL/KB proportions from the drawing.
            "drawingHints": [[str(h.l), str(h.b)] for h in p.hints],
        } for p in project.patterns],
    }


def save(project: Project, path: str | Path) -> None:
    """Write via a temporary file in the same folder, so a crash never leaves half a file."""
    path = Path(path)
    text = json.dumps(to_dict(project), indent=2, ensure_ascii=False)
    handle, temp = tempfile.mkstemp(prefix=".~", suffix=EXTENSION, dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.write("\n")
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


# --- reading -----------------------------------------------------------------

def _parse_form(value, where: str) -> LinearForm:
    if not isinstance(value, list) or len(value) != 3:
        raise ProjectFileError(f"{where}: expected three coefficients.")
    try:
        coeffs = [rational.check(Fraction(str(c))) for c in value]
    except (ValueError, ZeroDivisionError) as exc:
        raise ProjectFileError(f"{where}: invalid coefficient ({exc}).") from exc
    return LinearForm(*coeffs)


def _int(data: dict, key: str, where: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProjectFileError(f"{where}: '{key}' must be a whole number.")
    return value


def from_dict(data: dict) -> Project:
    if not isinstance(data, dict) or data.get("format") not in ACCEPTED_FORMATS:
        raise ProjectFileError("This is not a LayerForge project file.")
    version = data.get("schemaVersion")
    if not isinstance(version, int):
        raise ProjectFileError("The project file has no schema version.")
    if version > SCHEMA_VERSION:
        raise ProjectFileError(f"The project was saved by a newer version of the tool "
                               f"(schema {version}, supported up to {SCHEMA_VERSION}).")
    if version < 1:
        raise ProjectFileError(f"Unsupported schema version {version}.")

    pdfs = tuple(PdfRef(_int(r, "id", "PDF reference"), str(r.get("path", "")))
                 for r in data.get("pdfs", []))
    patterns = []
    for uid, raw in enumerate(data.get("patterns", []), start=1):
        where = f"Pattern {raw.get('patternId', '?')}"
        dims_raw = raw.get("dimensions", {})
        dims = Dimensions(_int(dims_raw, "KL", where), _int(dims_raw, "KB", where),
                          _int(dims_raw, "D", where), _int(dims_raw, "palletWidth", where),
                          _int(dims_raw, "palletLength", where))
        packages = []
        for n, k in enumerate(raw.get("packages", []), start=1):
            orientation = _int(k, "orientation", f"{where}, package {n}")
            if orientation not in ORIENTATIONS:
                raise ProjectFileError(f"{where}, package {n}: orientation must be 0 or 90.")
            packages.append(Package(_parse_form(k.get("x"), f"{where}, package {n}"),
                                    _parse_form(k.get("y"), f"{where}, package {n}"), orientation))
        src = raw.get("source")
        source = None
        if src is not None:
            rect = src.get("rect")
            if not (isinstance(rect, list) and len(rect) == 4):
                raise ProjectFileError(f"{where}: invalid source region.")
            source = SourceRef(_int(src, "pdf", where), _int(src, "page", where),
                               tuple(float(c) for c in rect))
        origin = raw.get("origin", Origin.MANUAL)
        verified = raw.get("verified")
        hints = []
        for hint in raw.get("drawingHints", []):
            if not (isinstance(hint, list) and len(hint) == 2):
                raise ProjectFileError(f"{where}: invalid drawing hint.")
            hints.append(_parse_form(hint + ["0"], f"{where}, drawing hint"))
        patterns.append(Pattern(uid, _int(raw, "patternId", where), tuple(packages), dims,
                                verified if isinstance(verified, str) else None, source,
                                origin if origin in Origin.ALL else Origin.MANUAL, tuple(hints)))
    return Project(str(data.get("name", "Untitled")), tuple(patterns), pdfs, len(patterns) + 1)


def display_name(path: str | Path) -> str:
    """File name without the project extension (current or former)."""
    name = Path(path).name
    for extension in (EXTENSION, *LEGACY_EXTENSIONS):
        if name.endswith(extension):
            return name[:-len(extension)]
    return Path(path).stem


def load(path: str | Path) -> Project:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProjectFileError(f"Cannot read the file: {exc.strerror or exc}.") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProjectFileError(f"The file is not valid JSON (line {exc.lineno}).") from exc
    return from_dict(data)
