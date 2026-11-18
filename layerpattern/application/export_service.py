"""Transactional export of Excel and TIA sources from one immutable snapshot.

All files are written into a temporary folder inside the target folder (same volume,
so the final move is an atomic rename), checked, and only then moved into place.
If anything fails, the target folder is left exactly as it was.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from layerpattern.domain.export_model import ExportSnapshot


class ExportError(Exception):
    """Export aborted; the target folder is unchanged. Message is meant for the user."""


@dataclass(frozen=True, slots=True)
class ExportRequest:
    folder: Path
    base_name: str
    excel: bool = True
    tia: bool = True


def safe_base_name(project_name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", project_name).strip("_")
    return base or "LayerPatterns"


def output_files(request: ExportRequest) -> dict[str, Path]:
    """Final paths by kind, in the order they are shown in the export dialog."""
    files: dict[str, Path] = {}
    if request.excel:
        files["excel"] = request.folder / f"{request.base_name}_Patterns.xlsx"
    if request.tia:
        files["types"] = request.folder / f"{request.base_name}_Types.udt"
        files["db"] = request.folder / f"{request.base_name}_Patterns.db"
    return files


def _check_writable(path: Path) -> None:
    if not path.exists():
        return
    try:
        # Opening for update fails while Excel or TIA keeps the file locked.
        with open(path, "r+b"):
            pass
    except PermissionError as exc:
        raise ExportError(f"{path.name} is open in another program or write-protected.") from exc


def export(snapshot: ExportSnapshot, request: ExportRequest) -> list[Path]:
    if not (request.excel or request.tia):
        raise ExportError("Select at least one export format.")
    if not request.folder.is_dir():
        raise ExportError(f"The target folder does not exist: {request.folder}")
    targets = output_files(request)
    for path in targets.values():
        _check_writable(path)

    from layerpattern.infrastructure import excel_export, tia_export, tia_import

    temp_dir = Path(tempfile.mkdtemp(prefix=".layerpattern-export-", dir=request.folder))
    try:
        staged: dict[str, Path] = {kind: temp_dir / path.name for kind, path in targets.items()}
        try:
            if request.excel:
                excel_export.write(snapshot, staged["excel"])
                excel_export.verify(staged["excel"], snapshot)
            if request.tia:
                types_text, db_text = tia_export.render(snapshot)
                staged["types"].write_bytes(tia_export.encode(types_text))
                staged["db"].write_bytes(tia_export.encode(db_text))
                _verify_tia(snapshot, staged["types"], staged["db"], tia_import)
        except ExportError:
            raise
        except Exception as exc:  # noqa: BLE001 - any failure aborts the transaction
            raise ExportError(f"Generating the export failed: {exc}") from exc
        _commit(staged, targets, temp_dir)
        return list(targets.values())
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _verify_tia(snapshot: ExportSnapshot, types_path: Path, db_path: Path, tia_import) -> None:
    types_text = types_path.read_bytes().decode("ascii")
    for name in (snapshot.names.package_type, snapshot.names.index_type):
        if f'TYPE "{name}"' not in types_text:
            raise ExportError(f"Type {name} missing in the generated type source.")
    imported = tia_import.parse(db_path.read_bytes().decode("ascii"))
    rows = [(r.orientation, r.kx, r.ky) for r in snapshot.packages]
    back = [row for pattern in imported.patterns for row in pattern.packages]
    if back != rows or [p.pattern_id for p in imported.patterns] != \
            [p.pattern_id for p in snapshot.patterns]:
        raise ExportError("The generated DB source does not read back identically.")


def _commit(staged: dict[str, Path], targets: dict[str, Path], temp_dir: Path) -> None:
    """Move staged files into place; on failure restore the previous state."""
    backups: dict[Path, Path] = {}
    placed: list[Path] = []
    try:
        for kind, final in targets.items():
            if final.exists():
                backup = temp_dir / (final.name + ".previous")
                os.replace(final, backup)
                backups[final] = backup
            os.replace(staged[kind], final)
            placed.append(final)
    except OSError as exc:
        for final in placed:
            final.unlink(missing_ok=True)
        for final, backup in backups.items():
            try:
                os.replace(backup, final)
            except OSError:
                pass
        raise ExportError(f"Moving the files into the target folder failed: {exc}") from exc
