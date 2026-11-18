# LayerForge

LayerForge turns pallet layer patterns into parameters for a PLC.

A layer pattern describes how cases are arranged on one layer of a pallet. LayerForge reads the
patterns from PDF drawings, lets you check and correct them in a CAD-like 2D editor, and exports
them as an Excel workbook and as source files for **Siemens TIA Portal V21**.

The exported positions are **symbolic**, not fixed millimetres. Every case centre is stored as
coefficients of the case length `KL`, the case width `KB` and the safety gap `D`:

```
RelativeCenterX = KxL*KL + KxB*KB + KxD*D
RelativeCenterY = KyL*KL + KyB*KB + KyD*D
```

So one pattern works for every case size: the PLC inserts the current `KL`, `KB` and `D` and
gets the positions relative to the pallet centre. The coefficients are exact multiples of 1/16
(0.25, -0.5, 1.0, ...), so they survive the trip into a `REAL` without rounding errors.

Windows 10/11 desktop application, Python + PyQt6.

## What it does

- **Read patterns from PDFs.** Vector drawings and scanned pages. Rectangles are detected by
  brightness and edges, not by colour; text, dimensions and arrows are ignored. Layer drawings are
  rarely to scale, so LayerForge reads which cases touch and which edges are flush and rebuilds
  the pattern from that topology. Results appear as proposals that you check before accepting.
- **Fit to pallet.** Suggests "round" values for `KL` and `KB` (such as 320 x 240) with which
  the pattern fits the pallet best. The arrangement stays as drawn: flush edges stay flush.
- **Edit.** A 2D editor with snapping (adjacent plus `D`, flush edges, centred), rotation,
  placement sequence, undo/redo, and a symbolic and a numeric view.
- **Validate and verify.** Overlaps, gaps smaller than `D`, cases not touching the rest, duplicate
  and mirrored patterns. Each pattern also shows the conditions under which its coefficients are
  valid (for example `2*KB + D >= KL`). Only patterns you have verified can be exported.
- **Export.**
  - `<prefix>_Patterns.xlsx`: one sheet with a row per pattern, one with a row per case.
  - `<prefix>_Types.udt` + `<prefix>_Patterns.db`: TIA Portal V21 external sources. Import
    them with the types first, then *Generate blocks from source*.
  - All files are written to a staging folder first, so a failed export changes nothing.
- **Re-import** a DB that LayerForge generated, to continue working on an existing project.

The full user guide is built in: press **F1** in the program.

## Requirements

| What | Version | Notes |
| --- | --- | --- |
| Windows | 10 or 11 | The build script uses Windows-only features (Start-menu shortcut). |
| Python | 3.13 (64-bit) | Developed and tested with 3.13. |
| Git | any recent | Needed to install QtControlsPyRS and for the version number of a build. |

All Python packages are listed in [requirements.txt](requirements.txt).

## Getting started

### 1. Clone and create a virtual environment

```powershell
git clone https://github.com/lCRAMl/LayerForge.git
cd LayerForge
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If PowerShell refuses to run `Activate.ps1`, allow local scripts for your user once with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Or use `cmd.exe` and
`.venv\Scripts\activate.bat` instead.

### 2. Install QtControlsPyRS

LayerForge's look comes from [QtControlsPyRS](https://github.com/lCRAMl/QtControlsPyRS), a
PyQt6 widget library by the same author. It provides the frameless dialogs, the command bar, the
status line, the tab widget and the compact input fields. It is not on PyPI, so install it
straight from GitHub (LayerForge needs version 0.4 or newer):

```powershell
pip install "qt-controls-pyrs @ git+https://github.com/lCRAMl/QtControlsPyRS.git"
```

To work on the library at the same time, clone it next to LayerForge and install it as
editable instead. Changes to the library then take effect without reinstalling:

```powershell
git clone https://github.com/lCRAMl/QtControlsPyRS.git ..\QtControlsPyRS
pip install -e ..\QtControlsPyRS
```

### 3. Install the other dependencies

```powershell
pip install -r requirements.txt
```

This installs the runtime packages (PyQt6, pypdfium2, OpenCV, numpy, openpyxl, Jinja2), the test
tools (pytest, pytest-qt, reportlab) and the build tools (PyInstaller, pywin32).

`requirements.txt` asks for `opencv-python-headless`. If the full `opencv-python` is already
installed in the environment, uninstall one of them: both provide the same `cv2` package and
break each other.

### 4. Run

```powershell
python run.py
```

In VS Code, open the folder, pick the `.venv` interpreter, choose **LayerForge** under
*Run and Debug* and press F5.

### 5. Run the tests

```powershell
python -m pytest
```

The suite takes about 15 s. Two recognition tests use real sample PDFs from
`tests/fixtures/private/`. Those files are not in the repository, so these tests are skipped.
`pytest.ini` sets `qt_api = pyqt6`, so the tests also work in an environment where PySide6 is
installed.

## Building the program

```powershell
python AUTOBUILD.py
```

Run it from the activated virtual environment, in the repository root. It takes a few minutes and
does the following:

1. Reads the version from git (`git describe --tags --long`, for example `v1.0.0-5-g745b112`) and
   writes it to `build_version.py`. This file is generated and not committed. The build therefore
   needs a git clone with its tags; a ZIP download builds as `0.0.0-0-unknown`. Started from
   source, the program shows the version `dev`.
2. Builds a **program folder** with PyInstaller: `output\LayerForge_<version>\` with
   `LayerForge_<version>.exe` and `_internal\`. A folder instead of a single EXE keeps the start at
   about one second; a single-file EXE would unpack around 150 MB on every start. The help, the
   TIA templates and the icon are bundled. PySide6, tkinter and the test packages are excluded.
3. Removes files that are bundled but never used (the OpenCV video DLL and Qt's software OpenGL,
   about 47 MB), then runs the built program's self-test. The self-test renders a PDF page and
   checks OpenCV, the TIA templates, the Excel writer, the help and the main window.
4. Creates or updates the Start-menu shortcut **LayerForge**, pointing to the new build.
   Windows does not let a program pin itself to Start. To get a tile, pin it once yourself:
   *Start > All apps > LayerForge > right-click > Pin to Start*. The shortcut name has no version
   in it, so the tile follows every later build.

To distribute the program, copy the whole `output\LayerForge_<version>\` folder; the EXE does
not run without `_internal\`. The target PC needs neither Python nor any of the packages above.

You can also run the self-test by hand on any installed copy:

```powershell
LayerForge_<version>.exe --selftest report.txt
```

The icon is generated from `layerforge/resources/icons/layerforge.svg`. After changing the SVG,
run `python tools/make_icon.py` to rewrite the `.ico` and the PNG.

## Settings and files

- Projects are saved as `*.layerforge.json`.
- Settings live in the registry under `HKEY_CURRENT_USER\Software\LayerForge\LayerForge`.
- LayerForge writes no log files.

## Project layout

```
layerforge/
  domain/          pure Python: no Qt, OpenCV, PDF, openpyxl, Jinja2 (enforced by tests/test_architecture.py)
    rational.py    coefficient policy: power-of-two denominators <= 16, exact REAL literals
    linear.py      LinearForm l*KL + b*KB + d*D with Fractions
    model.py       immutable Package, Pattern, Project (package order = placement sequence)
    geometry.py    exact evaluation in 1/16 mm, overlap/clearance/neighbours, symbolic bounding box,
                   validity conditions
    snapping.py    relation catalogue (adjacent + D, flush, centred, half step) and resolution
    reconstruct.py drawn rectangles -> symbolic pattern by topology (drawings are not to scale),
                   plus the drawing's KL/KB proportions ("hints", e.g. 3*KL = 4*KB)
    fitting.py     Fit to pallet: round KL/KB that keep the hints and fit the pallet best
    validation.py, duplicates.py, transform.py, sequence.py, operations.py, export_model.py
  application/     Qt-free use cases: undo (snapshot stack), incremental validator, export service
                   (staging folder + rollback), DB import
  infrastructure/  project JSON, Excel, TIA templates (Jinja2) and reader, PDF access (pypdfium2),
                   recognition (OpenCV)
  presentation/    Qt: main window, command bar, editor (view/items/controller), PDF workspace,
                   panels, dialogs, background TaskRunner, self-test
  resources/       offline help, icons
tests/             domain, infrastructure, recognition (synthetic PDFs), workers, GUI, golden TIA files
tools/make_icon.py SVG -> multi-size .ico
AUTOBUILD.py       build script (see above)
doc/DESIGN.md      design decisions
```

## Design rules for contributors

- **Immutable model, snapshot undo.** Every edit is a pure function `Project -> Project` executed via
  `ProjectSession.execute()`; undo swaps whole snapshots. Views detect changes by object identity.
- **Exact geometry.** Positions are `LinearForm`s; millimetres appear only when evaluating for the
  example values. Never store floats in the model.
- **Verification = fingerprint** of the exported data (PatternId, sequence, orientation,
  coefficients). Geometry edits clear it; example-value edits keep it unless they change the export.
- **Background work** goes through `presentation/workers.py`; tasks must not touch widgets.
  Each channel has a generation counter, so stale results are dropped.
- **TIA sources** are plain ASCII with CRLF and are generated only from the Jinja2 templates in
  `infrastructure/templates`. The golden files in `tests/golden` must be updated deliberately when the
  format changes (and the exchange format version raised if old DB imports must be told apart).
- **PyQt6 only.** Never import PySide6; mixing two Qt bindings in one process crashes.
- General-purpose widgets belong in QtControlsPyRS, not in this repository.

## License

Copyright (C) 2026 lCRAMl

LayerForge is free software: you can redistribute it and/or modify it under the terms of the
GNU General Public License, version 3, as published by the Free Software Foundation. It is
distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See [LICENSE](LICENSE) for the
full text.

LayerForge uses PyQt6, which is licensed under the GPL v3 as well.
