import json
import os
from datetime import datetime
from pathlib import Path

import pytest
from helpers import H, KB, KL, eu13, grid, pkg

from layerforge.application import export_service
from layerforge.application.db_import import project_from_db
from layerforge.application.export_service import ExportError, ExportRequest
from layerforge.domain import operations as ops
from layerforge.domain.export_model import TiaNames, build_snapshot, package_rows
from layerforge.domain.model import Dimensions, Origin, Project, SourceRef
from layerforge.infrastructure import excel_export, project_store, tia_export, tia_import
from layerforge.infrastructure.project_store import ProjectFileError

GOLDEN = Path(__file__).with_name("golden")
STAMP = datetime(2026, 11, 18, 17, 45, 0)
GOLDEN_GENERATOR = "LayerForge 1.0"


def golden_project() -> Project:
    """IDs with gaps, mixed orientations, a negative coefficient (EU13) and a brick bond."""
    project = Project(name="Golden Test – Kave")
    project, _ = ops.add_pattern(project, grid(1, 1), pattern_id=1, name="SINGLE")
    project, _ = ops.add_pattern(project, eu13(), pattern_id=3, name="EU13")
    brick = (pkg(KL, KB * 3 * H), pkg(KL * H, KB * H))
    project, _ = ops.add_pattern(project, brick, pattern_id=7, dims=Dimensions(d=0), name="BRICK 7")
    return project


def snapshot(project=None):
    return build_snapshot(project or golden_project(), TiaNames(), STAMP)


# --- project file ------------------------------------------------------------

def test_project_round_trip_is_exact(tmp_path):
    project, pdf = ops.add_pdf(golden_project(), "C:/pdfs/Kave_Layerpattern.pdf")
    project = project.with_pattern(
        project.patterns[1].__class__(**{**{f: getattr(project.patterns[1], f) for f in
                                            ("uid", "pattern_id", "packages", "dims", "verified")},
                                         "source": SourceRef(pdf, 2, (10.0, 20.0, 110.0, 90.5)),
                                         "origin": Origin.RECOGNIZED}))
    project = ops.verify(project, project.patterns[0].uid)
    path = tmp_path / ("p" + project_store.EXTENSION)
    project_store.save(project, path)
    loaded = project_store.load(path)
    assert loaded == project
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schemaVersion"] == 1 and data["format"] == "layerforge-project"
    assert [p["patternId"] for p in data["patterns"]] == [1, 3, 7]   # manual list order


def test_newer_schema_is_rejected(tmp_path):
    data = project_store.to_dict(golden_project())
    data["schemaVersion"] = 2
    path = tmp_path / ("new" + project_store.EXTENSION)
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ProjectFileError, match="newer version"):
        project_store.load(path)


@pytest.mark.parametrize("content, message", [
    ("{not json", "not valid JSON"),
    ('{"format": "other"}', "not a LayerForge"),
    ('{"format": "layerforge-project"}', "no schema version"),
])
def test_broken_files_are_reported(tmp_path, content, message):
    path = tmp_path / ("x" + project_store.EXTENSION)
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ProjectFileError, match=message):
        project_store.load(path)


def test_coefficients_outside_policy_are_rejected():
    data = project_store.to_dict(golden_project())
    data["patterns"][0]["packages"][0]["x"] = ["1/3", "0", "0"]
    with pytest.raises(ProjectFileError, match="invalid coefficient"):
        project_store.from_dict(data)


# --- Excel -------------------------------------------------------------------

def test_excel_structure_and_values(tmp_path):
    from openpyxl import load_workbook

    path = tmp_path / "out.xlsx"
    snap = snapshot()
    excel_export.write(snap, path)
    excel_export.verify(path, snap)
    wb = load_workbook(path)
    assert wb.sheetnames == ["Patterns", "Packages"]
    patterns, packages = wb["Patterns"], wb["Packages"]
    assert [c.value for c in patterns[1]] == excel_export.PATTERN_HEADERS
    assert [[c.value for c in row] for row in patterns.iter_rows(min_row=2)] == [
        [1, "SINGLE", 1, 1, "KL", "KB", "always"],
        [3, "EU13", 2, 3, "KL + KB + D", "2*KB + D", "2*KB + D >= KL"],
        [7, "BRICK 7", 5, 2, "1.5*KL", "2*KB", "always"],
    ]
    assert patterns.freeze_panes == "A2" and packages.freeze_panes == "A2"
    assert "Patterns" in patterns.tables and "Packages" in packages.tables
    # Package 3 = second row of EU13 (automatic order): the standing one,
    # X = KL + 0.5*KB + D, Y = -0.5*KL + 2*KB + D from the lower-left corner.
    row = [c.value for c in packages[4]]
    assert row[:3] == [3, 3, 90]
    assert row[3:9] == [1.0, 0.5, 1.0, -0.5, 2.0, 1.0]
    # Numeric cells (openpyxl reads a stored 0.0 back as int 0 - Excel has one number type).
    assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in row[3:9])
    assert all(packages.cell(4, col).number_format == "0.0###" for col in range(4, 10))
    assert row[9:] == ["KL + 0.5*KB + D", "-0.5*KL + 2*KB + D"]
    # Brick bond: the lower package comes first although it was added second.
    assert [packages.cell(r, 4).value for r in (6, 7)] == [0.5, 1.0]


# --- TIA ---------------------------------------------------------------------

def test_tia_sources_match_golden_files():
    types, db = tia_export.render(snapshot(), generator=GOLDEN_GENERATOR)
    for name, text in (("golden_Types.udt", types), ("golden_Patterns.db", db)):
        expected = (GOLDEN / name).read_bytes()
        assert tia_export.encode(text) == expected, f"{name} differs from the golden file"


def test_tia_sources_are_ascii_crlf():
    types, db = tia_export.render(snapshot())
    for text in (types, db):
        data = tia_export.encode(text)
        data.decode("ascii")
        assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")
    assert "Kave" in db and "–" not in db          # umlaut/dash transliterated


def test_db_import_round_trip():
    snap = snapshot()
    _types, db = tia_export.render(snap)
    imported = tia_import.parse(db)
    assert imported.db_name == "DB_LayerPatterns"
    assert [p.pattern_id for p in imported.patterns] == [1, 3, 7]
    project = project_from_db(imported, Dimensions())
    original = golden_project()
    for a, b in zip(project.patterns[:2], original.patterns[:2]):
        assert package_rows(a) == package_rows(b)
        assert a.name == b.name
        assert a.origin == Origin.DB_IMPORT and a.verified is None


def test_db_import_rejects_foreign_files():
    with pytest.raises(tia_import.DbImportError, match="not generated by this tool"):
        tia_import.parse('DATA_BLOCK "X"\nBEGIN\nEND_DATA_BLOCK\n')
    _types, db = tia_export.render(snapshot())
    with pytest.raises(tia_import.DbImportError, match="version"):
        tia_import.parse(db.replace("LayerPattern-TIA 1", "LayerPattern-TIA 2"))
    # A DB of an earlier LayerForge (no names, centre reference) is refused.
    nameless = "\n".join(line.replace("PatternIndex[3].PatternName := 'EU13'; ", "") for line in db.splitlines())
    with pytest.raises(tia_import.DbImportError, match="no name"):
        tia_import.parse(nameless)
    broken = db.replace("Package[5].KyD := ", "Package[5].Kxx := ")
    with pytest.raises(tia_import.DbImportError, match="incomplete"):
        tia_import.parse(broken)


# --- transactional export ----------------------------------------------------

def request(folder, **kw):
    return ExportRequest(folder, "Golden", **kw)


def test_export_writes_all_three_files(tmp_path):
    files = export_service.export(snapshot(), request(tmp_path))
    assert sorted(f.name for f in files) == ["Golden_Patterns.db", "Golden_Patterns.xlsx",
                                             "Golden_Types.udt"]
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(f.name for f in files)


def test_export_tia_only(tmp_path):
    export_service.export(snapshot(), request(tmp_path, excel=False))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Golden_Patterns.db", "Golden_Types.udt"]


def test_failed_move_leaves_previous_files_untouched(tmp_path, monkeypatch):
    old = {name: f"old {name}".encode() for name in
           ("Golden_Patterns.xlsx", "Golden_Types.udt", "Golden_Patterns.db")}
    for name, content in old.items():
        (tmp_path / name).write_bytes(content)

    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        # Fail when the second new file is moved into place.
        if Path(dst).parent == tmp_path and not str(src).endswith(".previous"):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("disk full")
        return real_replace(src, dst)

    monkeypatch.setattr(export_service.os, "replace", flaky)
    with pytest.raises(ExportError, match="disk full"):
        export_service.export(snapshot(), request(tmp_path))
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == old


def test_failed_generation_leaves_no_files(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("template broken")

    monkeypatch.setattr(tia_export, "render", boom)
    with pytest.raises(ExportError, match="template broken"):
        export_service.export(snapshot(), request(tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_export_needs_a_format_and_a_folder(tmp_path):
    with pytest.raises(ExportError):
        export_service.export(snapshot(), request(tmp_path, excel=False, tia=False))
    with pytest.raises(ExportError):
        export_service.export(snapshot(), request(tmp_path / "missing"))


def test_safe_base_name():
    assert export_service.safe_base_name("Kave EU / Linie 2") == "Kave_EU_Linie_2"
    assert export_service.safe_base_name("äöü") == "LayerPatterns"


def test_drawing_hints_survive_save_and_load(tmp_path):
    from layerforge.domain.linear import LinearForm

    project, uid = ops.add_pattern(Project(name="h"), grid(2, 1), hints=(LinearForm.of(3, -4),))
    path = tmp_path / ("h" + project_store.EXTENSION)
    project_store.save(project, path)
    loaded = project_store.load(path)
    assert loaded.pattern(uid).hints == (LinearForm.of(3, -4),)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["patterns"][0]["drawingHints"] == [["3", "-4"]]
    del data["patterns"][0]["drawingHints"]                    # files without hints still load
    assert project_store.from_dict(data).patterns[0].hints == ()


def test_projects_of_the_former_name_still_open(tmp_path):
    """Files saved as LayerPattern Tool (*.layerpattern.json) open in LayerForge."""
    data = project_store.to_dict(golden_project())
    data["format"] = "layerpattern-project"
    path = tmp_path / "old.layerpattern.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert project_store.load(path) == golden_project()
    assert project_store.display_name(path) == "old"
    assert project_store.display_name(tmp_path / ("new" + project_store.EXTENSION)) == "new"
