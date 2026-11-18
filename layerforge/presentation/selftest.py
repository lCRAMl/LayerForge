"""`LayerForge.exe --selftest [report]`: proves that a build contains everything.

AUTOBUILD.py runs it on the freshly built program. Each check touches one part that
PyInstaller can miss: the PDFium DLL, OpenCV, the Jinja2 templates and the help file
(data files), openpyxl, and the main window itself. The report is only written when a
path is given - normal runs write no files.
"""

from __future__ import annotations

import os
import tempfile
import traceback
from datetime import datetime
from pathlib import Path


def _pdfium() -> str:
    import pypdfium2 as pdfium

    from layerforge.infrastructure.pdf_source import PDFIUM_LOCK
    with PDFIUM_LOCK:
        pdf = pdfium.PdfDocument.new()
        page = pdf.new_page(200, 100)
        bitmap = page.render(scale=1)
        shape = bitmap.to_numpy().shape
        bitmap.close()
        page.close()
        pdf.close()
    return f"rendered {shape}"


def _opencv() -> str:
    import cv2
    import numpy as np

    edges = cv2.Canny(np.zeros((40, 40), np.uint8), 10, 30)
    return f"cv2 {cv2.__version__}, canny {edges.shape}"


def _snapshot():
    from layerforge.domain import operations as ops
    from layerforge.domain.export_model import TiaNames, build_snapshot
    from layerforge.domain.linear import KB, KL
    from layerforge.domain.model import Package, Project

    project, _uid = ops.add_pattern(Project(name="Selftest"),
                                    (Package(KL.half(), KB.half(), 0),), pattern_id=1)
    return build_snapshot(project, TiaNames(), datetime.now())


def _tia() -> str:
    from layerforge.infrastructure import tia_export, tia_import

    types, db = tia_export.render(_snapshot())
    tia_import.parse(db)
    return f"type source {len(types)} chars, DB reads back"


def _excel() -> str:
    from layerforge.infrastructure import excel_export

    handle, name = tempfile.mkstemp(suffix=".xlsx")
    os.close(handle)
    try:
        excel_export.write(_snapshot(), name)
        excel_export.verify(name, _snapshot())
    finally:
        os.remove(name)
    return "workbook written and read back"


def _resources() -> str:
    from layerforge.presentation.help_tab import HELP_FILE
    from layerforge.presentation.icons import APP_ICON

    missing = [p for p in (HELP_FILE, APP_ICON) if not Path(p).exists()]
    if missing:
        raise FileNotFoundError(", ".join(map(str, missing)))
    return "help and icon present"


def run(app, report: str | None) -> int:
    from layerforge.presentation.main_window import MainWindow
    from layerforge.presentation.settings import AppSettings

    results = []
    for name, check in (("PDFium", _pdfium), ("OpenCV", _opencv), ("TIA templates", _tia),
                        ("Excel", _excel), ("Resources", _resources)):
        try:
            results.append((name, True, check()))
        except Exception:  # noqa: BLE001 - every failure is reported, none stops the others
            results.append((name, False, traceback.format_exc()))
    try:
        window = MainWindow(AppSettings())
        window.show()
        app.processEvents()
        window.hide()
        results.append(("Main window", True, "built and shown"))
    except Exception:  # noqa: BLE001
        results.append(("Main window", False, traceback.format_exc()))
    ok = all(passed for _n, passed, _d in results)
    if report:
        lines = [f"{'OK  ' if passed else 'FAIL'} {name}: {detail}" for name, passed, detail in results]
        Path(report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1
