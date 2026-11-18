"""Layering rules from the specification, enforced statically."""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "layerpattern"
HEAVY = {"PyQt6", "PySide6", "cv2", "pypdfium2", "fitz", "openpyxl", "jinja2", "numpy"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def test_domain_imports_no_frameworks():
    for path in (PACKAGE / "domain").glob("*.py"):
        assert not _imports(path) & HEAVY, f"{path.name} imports {_imports(path) & HEAVY}"


def test_application_layer_is_qt_free():
    for path in (PACKAGE / "application").glob("*.py"):
        assert not _imports(path) & {"PyQt6", "PySide6"}, path.name


def test_pyside_is_never_used():
    for path in PACKAGE.rglob("*.py"):
        assert "PySide6" not in _imports(path), path.name
