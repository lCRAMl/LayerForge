# LayerPattern Tool

Desktop tool (Windows 10/11, PyQt6) that turns pallet layer patterns from PDF drawings into
symbolic PLC parameters: every package centre is `Kx·KL + Kx·KB + Kx·D` relative to the pattern
centre. Patterns are reviewed in a CAD-like editor and exported to Excel and TIA Portal V21 sources.

User help: press F1 in the tool (`layerpattern/resources/help/index.html`).

## Run

Requirements: Python 3.13, the in-house widget library and a few packages.

```
pip install -e Z:\Code\python\QtControlsPyRS
pip install PyQt6 pypdfium2 numpy openpyxl Jinja2 pytest pytest-qt reportlab
```

OpenCV: the full `opencv-python` already present on the development machine is fine. On a fresh
machine install `opencv-python-headless` instead - never both (they share the `cv2` package).

- VS Code: open this folder, choose **LayerPattern Tool** in *Run and Debug*, press F5.
- Terminal: `python run.py`
- Tests: `python -m pytest` (≈ 10 s). `pytest.ini` pins `qt_api = pyqt6`, because PySide6 is installed too.

Settings live in the registry: `HKEY_CURRENT_USER\Software\LayerPattern\LayerPatternTool`.
No log files are written.

## Structure

```
layerpattern/
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
                   panels, dialogs, background TaskRunner
  resources/help/  offline help
tests/             domain, infrastructure, recognition (synthetic PDFs), workers, GUI, golden TIA files
tests/fixtures/private/  real PDFs for optional tests (not committed)
doc/DESIGN.md      design decisions; PROGRESS.md: work log and decisions D1..D21
```

## Design rules worth knowing before changing code

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
- Library extensions (`HaloCommandBar`, `StatusBar.show_message`, lazy import) live in QtControlsPyRS.
