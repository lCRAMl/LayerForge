# LayerPattern Tool – Analysis and Design Proposal

Status: **approved and implemented** (2026-11-18). Decisions D1-D21 in `../PROGRESS.md`; implementation notes in section 10.
Source of truth for requirements: `../../Claude_Code_Prompt_Layerpattern_Tool.txt`.
Open decisions are tracked in `../PROGRESS.md` (section "Decisions").

---

## 1. Repository inspection

| Item | Finding | Consequence |
| --- | --- | --- |
| Repository | The spec folder is **not** a git repository. It holds V1–V3 of the earlier gantry/PLC work (old parameter model, not reused). | New tool goes into its own folder, proposed `LayerPatternTool/` (+ optional `git init`). |
| Custom Qt library | `<CUSTOM_QT_WIDGET_LIBRARY>` = **QtControlsPyRS** (https://github.com/lCRAMl/QtControlsPyRS, `qt_controls_pyrs` 0.4.0, PyQt6, editable install, own git repo, German docs/comments). | Usable; needs small extensions (section 4). |
| Existing Qt GUI in repo | None. Only the external library. | App shell is new. |
| Existing TIA V21 generation | `V3/python/gen_v3.py` writes DB sources by string building; V2 sources were imported successfully. Conventions: ASCII only, **CRLF** (V2, imported OK; V3 uses LF and is not yet compiled), `{ S7_Optimized_Access := 'TRUE' }`, `VERSION : x.y`, `NON_RETAIN`, start values as assignments after `BEGIN`, `//` comment headers, `TYPE "…" … STRUCT … END_STRUCT; END_TYPE`. | Reuse syntax conventions only; new names/fields; Jinja2 templates instead of string building. |
| Python | 3.13.5 (also 3.10). Library requires ≥ 3.10. | Python 3.13 – no conflict. |
| Installed | PyQt6 6.11, numpy 2.2.6, opencv-python 4.12 (full, not headless), openpyxl 3.1.5, Jinja2 3.1.6, pytest 9.1, pytest-qt 4.5, reportlab 5.0, Pillow. **PySide6 6.9 is also installed.** **PyMuPDF is not installed.** | See section 5. |
| pytest-qt | Default binding detection picks **PySide6** in this environment (verified). | `pytest.ini` must set `qt_api = pyqt6`. PySide6 is never imported. |
| Library import time | `import qt_controls_pyrs` ≈ 280 ms, of which ≈ 180 ms is `requests` (pulled in by the ImgBB upload helper via `referencethumb`). PyQt6.QtWidgets ≈ 30 ms. | Make `imgbb`/`ReferenceThumb` lazy in the library (backward compatible). |
| Sample PDFs | `Kave_Layerpattern.pdf`: 4 pages, PowerPoint export, **one embedded raster image per page** (~960 px wide), no fonts, 18 patterns (filled rectangles with small gaps, mixed orientations, labels/pills in the same colour). `Pallet-formats.pdf`: 2 pages, Excel export, **pure vector** (146 rectangle operators, lines drawn as thin rectangles), 4 patterns (outlined touching rectangles, one pattern with an internal hole). | Both recognition paths are needed; both become optional private fixtures with golden counts (18 patterns: 1,2,4,6,8,2,3,9,6,3,7,10,4,5,9,5,5,6 packages; 4 patterns: 28,15,22,12). |

### Key observation from the real PDFs

The drawings are **schematic, not to scale**. In `Pallet-formats.pdf` page 1 the same
case is drawn as 53 × 68 px when standing and 80 × 45 px when lying (aspect 1.28 vs 1.78).
The pattern outline is square although the pallet is 1000 × 1200 mm. A numeric
"normalise to the nearest symbolic position for KL/KB/D" therefore cannot work for such
sources. Recognition must derive the **topology** (who touches whom, which edges are
flush) and only then evaluate it with KL/KB/D (section 7).

---

## 2. Workflow in my own words

1. Start → Start page (New, Open, Import generated DB, five recent projects).
2. Project holds patterns (PatternId 1..99, stable) plus references to source PDFs.
3. PDF tab: import PDFs → thumbnails (background) → select pages → recognise whole
   page(s) or a drawn region (background, cancellable) → proposals are overlaid with
   none/yellow/red warning → user explicitly accepts proposals → they become patterns
   (one undoable command) with a source reference (pdf, page, region).
4. Editor tab: pattern list (ID, verified, count, duplicate/similar badge, preview,
   hover preview) + CAD-like editor + properties. User corrects packages (move with
   symbolic snapping, rotate 0/90, add, duplicate-and-place, delete, group move),
   edits the placement sequence (list drag & drop or click order), checks symbolic or
   numeric dimensions, enters real KL/KB/D/pallet values for the pattern.
5. Validation runs continuously (debounced); Verify is enabled only when the pattern is
   structurally valid and not an exact duplicate; verification shows a summary first.
6. Total-pattern rotation (in place or as rotated copy with new PatternId).
7. Save project (JSON). Export (Excel and/or TIA type+DB sources) is enabled only when
   every pattern is valid and verified; export writes transactionally.
8. A previously exported DB can be imported as a new project (patterns unverified).

---

## 3. Contradictions, gaps, risks

| # | Topic | Issue | Proposal |
| --- | --- | --- | --- |
| C1 | Verification vs. KL/KB/D | Spec: KL/KB/D changes never reset verification **and** any change to exported data resets it. For non-rectangular outlines the bounding box is a `max()` of competing edges (EU13: height = max(2·KB + D, KL)). A KL/KB/D change can switch the extreme edge, which shifts the pattern centre and changes **all** exported coefficients. | Store verification as a **fingerprint of the exported data** (PatternId, sequence, BaseOrientation, 6 coefficients per package). Verified ⇔ fingerprint matches. KL/KB/D edits keep verification unless they actually change the export. Implements "any change to exported data resets verification" generically. |
| C2 | Regime validity | Same root cause: coefficients are only correct for the KL/KB/D ordering they were derived for. | Compute and show **validity conditions**: the linear inequalities under which the chosen bounding-box edges stay extreme, e.g. "valid while KL < 2·KB + D". Inequalities that hold for every KL ≥ KB > 0, D ≥ 0 are dropped. Shown in properties and verify summary, not exported. |
| C3 | Recognition normalisation | "Normalise within strict tolerance" assumes drawings to scale; real PDFs are schematic (section 1). | Topological reconstruction (section 7). The strict tolerance applies to topology evidence (flush edges, small gaps), not to millimetres. |
| C4 | PatternIndex size | "Array 1 .. highest current PatternId" changes the DB layout whenever the highest ID changes; PLC code indexing an ID above the bound faults. | Fixed `Array[1..99]` (396 bytes); empty entries 0/0. Layout stable, any valid ID indexable. Needs approval (deviates from spec). |
| C5 | Complete pattern DB type | A UDT holding both arrays must be rebuilt in TIA whenever the package count changes. | No whole-DB UDT. Arrays are declared directly in the DB. PLC FCs can take `Array[*] of "<package type>"` as InOut. Type source = two stable UDTs. |
| C6 | Clearance | Spec forbids overlap only. Two facing packages with 0 ≤ gap < D (when D > 0) violate the safety gap physically. | Blocker "insufficient gap". |
| C7 | Pallet axes | "Pallet width / length" and default "1200 × 800" do not say which is X. | X = width = 1200, Y = length = 800 by default (landscape as in the Kave PDF); "swap pallet" button. |
| C8 | Normalisation undo | Recognised pixel positions are never project data, so there is nothing to undo "back to". | Accepting a proposal (already normalised) is one undoable command; undo removes it again. |
| C9 | Sequence values | Duplicate/missing sequence values are listed as blockers. | Sequence = order of the package tuple. Duplicates/gaps are impossible by construction; the check stays only as an import guard. |
| C10 | "Large internal whitespace" | Not separately definable without contradicting U/ring shapes. | Covered by the connectivity rule; no extra rule. |
| R1 | PyMuPDF licence | AGPL-3.0 (or commercial). Passing on a packaged EXE to customers/third parties triggers source-disclosure obligations. | Prefer **pypdfium2** (Apache-2.0/BSD-3, PDFium) unless the tool stays strictly internal (section 5). |
| R2 | PDF thread safety | Neither PyMuPDF nor PDFium document handles may be shared across threads. | Each background task opens its own document handle. |
| R3 | False proposals | Kave pages contain label pills and a header bar in the package colour. | Filters (rectangularity, holes from text, size relative to cluster); remaining ones appear as red/yellow proposals that the user simply does not accept. Region recognition is the clean path for busy pages. |
| R4 | Touching packages without separators | Splitting a solid blob is guesswork. | Split only when the blob is a near-perfect n×m multiple of the dominant package size; always yellow. |
| R5 | HaloTabWidget | Content slides with blur for 430 ms and blocks clicks meanwhile – tiring in a tool that switches PDF ↔ Editor often. | App subclass with shorter slide (≈ 180 ms) and less blur; no library change. |
| R6 | Network drive | App and library run from a mapped network drive (SMB share). | Lazy imports of heavy modules; `__pycache__` on the share works. |
| R7 | pytest-qt binding | Picks PySide6 by default here. | `qt_api = pyqt6` in `pytest.ini`. |

---

## 4. QtControlsPyRS gap analysis

Available and used: `HaloTabWidget` (main tabs), `StatusBar` (floating status line),
`Compact*` controls (dense forms), `IntField`/`CompactIntField` (mm fields with
`set_error`/`set_warning`), `HaloGroupBox`, `ResultGrid`/`WideResultGrid` (read-only
coefficients), `FrameToggle`/`LineToggle`/`HaloCheckBox` (display options),
`HaloRadioButton` (Symbolic/Numeric), `PulseHaloButton` (busy state for recognition),
`HaloScrollBar` (lists), `StaleBanner` (re-recognition comparison), `HaloButton`
(start page), `flash_taskbar` (long recognition finished while window is in background).

Missing:

| # | Element | Proposal |
| --- | --- | --- |
| L1 | Lazy import of `imgbb`/`ReferenceThumb` (removes `requests` from startup, −180 ms for every app using the library) | Library change, PEP 562 `__getattr__`, fully backward compatible. |
| L2 | Ribbon/command bar: grouped tool buttons (icon + text), checkable modes, drop-down commands, group captions, shortcut tooltips, enabled state from `QAction` | New `HaloCommandBar` in the library (QAction-driven, palette-based like the rest). |
| L3 | Status message levels (info/warning/error colour) and an optional "Details…" action for unexpected errors | Extend `StatusBar` (`show_message(text, level, details=None)`; `setText` unchanged). |
| L4 | Icons | App-local inline SVG paths rendered through `QSvgRenderer`, coloured from the palette; no image files. |

Everything else (lists with delegates and drag & drop, splitters, dialogs, help viewer
`QTextBrowser`) is plain PyQt6 and needs no library work.

---

## 5. Library evaluation

| Library | Verdict | Notes |
| --- | --- | --- |
| PyQt6 | keep | Already used by the library. PySide6 must never be imported. |
| QtControlsPyRS | keep | + L1–L3. |
| QGraphicsView/Scene | keep | No OpenGL viewport. |
| PyMuPDF | **alternative proposed** | AGPL. Convenient vector API (`get_drawings`). |
| pypdfium2 | **recommended** | Apache/BSD, small, fast import, excellent rendering incl. clip regions, page objects (paths with bounds, images with extraction), Python-version independent wheels. Vector inspection is less convenient but sufficient (Excel draws lines as thin rectangles; raw segment API available). |
| OpenCV | keep the installed `opencv-python` | Installing `-headless` additionally collides (both provide `cv2`). On Windows `opencv-python` has no Qt plugin conflict. Imported lazily in workers only. |
| NumPy | keep | Recognition only; lazy. The domain does not need it. |
| openpyxl | keep | Lazy at export. |
| Jinja2 | keep | Two small templates; lazy at export. |
| dataclasses + Fraction | keep | Frozen dataclasses, exact `Fraction`. |
| Decimal | drop | All inputs are integers; REAL literals are produced exactly from `Fraction`. |
| pytest / pytest-qt | keep | Few focused GUI tests. |
| reportlab | test-only | Generates synthetic vector PDFs for recognition tests (already installed). |

---

## 6. Architecture

### 6.1 Layers and packages

```
LayerPatternTool/
  run.py                          entry point (VS Code launch config)
  layerpattern/
    domain/                       pure Python, no Qt/OpenCV/PDF/openpyxl/Jinja2
      linear.py                   LinearForm(l, b, d) with Fraction coefficients
      model.py                    Package, Pattern, Project, SourceRef (frozen)
      geometry.py                 extents, bbox regime, overlap, adjacency, clearance
      snapping.py                 relation catalogue, candidate generation
      validation.py               blockers, warnings, validity conditions
      duplicates.py               canonical keys, duplicate/mirror detection
      transform.py                total rotation 90/180/270
      sequence.py                 automatic order, reorder helpers
      reconstruct.py              recognised rectangles -> symbolic pattern (topology)
      export_model.py             immutable export snapshot, fingerprint, REAL literals
    application/                  use cases; Qt-free
      undo.py                     snapshot undo stack
      commands.py                 project edits as pure functions
      tasks.py                    progress/cancel protocol for background work
      export_service.py           snapshot + transactional writing
    infrastructure/
      project_store.py            JSON load/save + schema versions
      excel_export.py             openpyxl
      tia_export.py, templates/   Jinja2 type + DB source
      tia_import.py               parser for our own generated DB format only
      pdf_source.py               PDF backend wrapper (render, images, vector rects)
      recognition/                OpenCV pipeline -> rectangles + groups
    presentation/
      app.py, theme.py, icons.py, main_window.py, start_page.py
      editor/ (view, scene, items, controller, dimensions)
      pdf/ (thumbnails, page view, proposals)
      pattern_list.py, properties.py, sequence_panel.py, dialogs/, help_tab.py
      workers.py                  QThreadPool bridge with generation counters
    resources/help/index.html
  tests/ (domain, application, infrastructure, recognition, a few gui)
  tests/fixtures/private/         real PDFs, optional, skipped when absent
```

### 6.2 GUI architecture options

**A – Immutable document + snapshot undo + thin presenters (recommended)**
The project is an immutable value (frozen dataclasses, tuples). Every edit is a pure
function `Project -> Project`. A small `ProjectSession` (QObject) holds the current
project and an undo stack of (label, before, after) snapshots; structural sharing makes
snapshots nearly free (≤ 99 patterns × ≤ 64 packages). Views subscribe to
`projectChanged(old, new)` and update incrementally by identity diff (`old_pattern is
new_pattern`). Presenters/controllers translate UI intents into commands. QGraphicsItems
only paint and report mouse intents.
+ trivially correct undo/redo (no inverse operations), domain fully testable,
  little code. − whole-pattern replacement per edit (irrelevant at this size).

**B – MVVM-like presentation models**
Mutable domain objects wrapped in QObject view models with per-property signals,
`QUndoCommand`s with explicit redo/undo. + very fine-grained updates. − PyQt has no
data binding, so much boilerplate; every command needs a correct inverse.

**C – Passive-view MVP**
Views implement interfaces, presenters own all logic. + maximal testability.
− most code; heavy for a single-user engineering tool.

### 6.3 Background work

`QThreadPool` + `QRunnable`; a task is a Qt-free callable `(progress, cancel) -> result`.
Each channel (thumbnails, recognition) has a generation counter; a result is applied only
when its generation is still current (page/region/project unchanged). Cancellation via a
token checked between stages/pages. Workers create `QImage`/NumPy data only; conversion to
`QPixmap` and any scene mutation happen on the GUI thread. Errors return a short message
plus traceback (status bar + Details).

### 6.4 Performance measures

- Window visible before any heavy import; PDF backend, OpenCV, NumPy, openpyxl, Jinja2
  are imported on first use.
- Library lazy import (L1).
- Validation uses exact integer arithmetic in units of 1/16 mm (all coefficients have
  power-of-two denominators ≤ 16, KL/KB/D are integers) – exact and fast.
- During drag only the moving items, snap guides and the selected-package dimensions
  update; full validation is debounced (~80 ms) after release.
- Snap candidates are precomputed as floats at drag start; exact forms only on commit.
- One dimension overlay item paints all dimensions; text uses
  `ItemIgnoresTransformations`.
- Pattern previews are `QImage`s cached by geometry key.
- Thumbnails rendered progressively in the background, cached in memory.

---

## 7. Domain model

- `LinearForm(l, b, d)`: value = l·KL + b·KB + d·D, `Fraction` coefficients.
- `Package(x, y, orientation)`: centre as LinearForms in pattern coordinates
  (X right, Y up), orientation 0 (KL along X) or 90 (KL along Y).
- `Pattern(pattern_id, packages, kl, kb, d, pallet_x, pallet_y, verified_fp, source,
  origin, name)`: the order of `packages` has no meaning (since 2026-11-20; before, it was
  the placement sequence). `name` is what the MFC sends; the PLC looks it up.
- Export coefficients = package centre − lower-left bounding-box corner (since 2026-11-20;
  before: − bounding-box centre). The bounding box takes, per side, the package edge that
  is extreme for the pattern's current KL/KB/D; ties are broken by the simplest form
  (smallest coefficients).
- REAL literals: denominators limited to powers of two ≤ 16 → exact decimal with at most
  4 places, always a decimal point (`1.0`, `-0.5`, `0.1875`), never `-0.0`; exactly
  representable as IEEE single, so the PLC sees no rounding.

### 7.1 Validation

Blockers: no packages; > max count (default 64, Options); overlap; insufficient gap
(proposed C6); disconnected orthogonal neighbour graph (neighbours: gap exactly D and
positive projection overlap); non-representable coefficient; invalid orientation;
duplicate PatternId; exact geometric duplicate. Notes (non-blocking): KL = KB
(orientation indeterminate), mirrored similarity, validity conditions, overhang (only
on request).

### 7.2 Snapping relations (per axis, to a reference package)

Priority order: adjacent with one D (before/after) → flush edges (min/min, max/max) →
centres aligned → half-step (centre on edge, edge on centre). Snap target per axis =
nearest candidate within the screen snap radius; on release there is always a
resolved relation. Ties within 2 px prefer the higher priority, then smaller
coefficients. Group move snaps the package under the cursor and applies the same
symbolic delta to the whole selection. Rotation (R) rotates about the centre and then
re-snaps at the same spot.

### 7.3 Recognition → symbolic (topology)

1. Orientation per rectangle from its aspect ratio (0 if wider than high).
2. Size clustering (long and short side medians, ±10 %) → outliers yellow.
3. Evidence per pair: adjacency (gap ≤ small threshold relative to the short side,
   projection overlap) and flush edges/centres (difference ≤ tolerance).
4. Solve X and Y separately by a best-first traversal from the top-left package using
   the relation priority above; with several left/upper neighbours the one giving the
   larger offset is used (prevents overlap for any KL/KB/D).
5. Evaluate with KL/KB/D (defaults or values typed in the PDF tab) → validation →
   warning level.

---

## 8. Siemens data structure (template-backed)

Naming sets (choose one; editable later in Options, shown in the export dialog):

| Element | Set A (V3 prefix style) | Set B (short namespace) | Set C (Siemens style-guide-like) |
| --- | --- | --- | --- |
| Package type | `UDT_LayerPackage` | `LP_Package` | `typLayerPackage` |
| Pattern index type | `UDT_LayerPatternIndex` | `LP_PatternIndex` | `typLayerPatternIndex` |
| Whole-DB type | not needed (C5) | not needed | not needed |
| Global DB | `DB_LayerPatterns` | `LP_Patterns` | `LayerPatterns` |

Type source (`<Project>_Types.udt`, ASCII, CRLF):

```
// GENERATED FILE - DO NOT EDIT. Re-export with LayerPattern Tool.
// Generator: LayerPattern Tool 1.0
// Format: LayerPattern-TIA 1
// Generated: 2026-11-18 17:45:00
// Project: <name>
TYPE "UDT_LayerPackage"
VERSION : 1.0
   STRUCT
      BaseOrientation : USInt;   // 0 = KL along X, 90 = KL along Y
      KxL : Real;                // RelativeCenterX = KxL*KL + KxB*KB + KxD*D
      KxB : Real;
      KxD : Real;
      KyL : Real;                // RelativeCenterY = KyL*KL + KyB*KB + KyD*D
      KyB : Real;
      KyD : Real;
   END_STRUCT;
END_TYPE

TYPE "UDT_LayerPatternIndex"
VERSION : 1.0
   STRUCT
      FirstPackageIndex : UInt;  // 0 = no pattern with this PatternId
      PackageCount : UInt;
   END_STRUCT;
END_TYPE
```

DB source (`<Project>_Patterns.db`):

```
// (same header)
DATA_BLOCK "DB_LayerPatterns"
{ S7_Optimized_Access := 'TRUE' }
VERSION : 1.0
NON_RETAIN
   VAR
      PatternIndex : Array[1..99] of "UDT_LayerPatternIndex";
      Package : Array[1..<N>] of "UDT_LayerPackage";
   END_VAR

BEGIN
   PatternIndex[1].FirstPackageIndex := 1;
   PatternIndex[1].PackageCount := 4;
   Package[1].BaseOrientation := 0;
   Package[1].KxL := -0.5;
   ...
END_DATA_BLOCK
```

Access: `Package[PatternIndex[id].FirstPackageIndex + Sequence - 1]`. Global package
indices are not stable identifiers (they compact after deletions).

---

## 9. Phases (proposed adjustment)

| Phase | Content | Test gate |
| --- | --- | --- |
| 0 | Library: L1 lazy import, L2 `HaloCommandBar`, L3 status levels (+ library tests, README, CHANGELOG) | library test suite green |
| 1 | Domain core, reconstruction, validation, duplicates, rotation, project JSON, Excel, TIA templates, DB import, transactional export service | domain/application/infrastructure tests green |
| 2 | App shell (main window, command bar, tabs, start page, status, Options/QSettings, New/Open/Save/Save As), pattern list with previews, editor (items, snapping, dimensions, pallet, sequence, undo/redo, rotations), properties, verify | + focused GUI tests |
| 3 | PDF workspace: import, thumbnails, page view, region selection, recognition pipeline, proposals, acceptance, source view, relink | + synthetic PDF tests, optional private fixtures |
| 4 | Export dialog, help tab/F1, error details, full workflow pass, run instructions, developer notes | all tests green, acceptance list |

Moving the app shell into phase 2 lets the editor be exercised in the real window; the
library work comes first because the shell depends on it.

---

## 10. Implementation notes (deviations and findings)

- **PDFium is not thread-safe across documents.** Concurrent calls from two threads corrupted the heap
  (0xc0000374). `infrastructure/pdf_source.py` serialises every PDFium call with one process-wide lock and
  closes pages and bitmaps explicitly inside it. OpenCV work stays parallel. (Updates R2.)
- **Verification:** geometry, sequence, orientation and PatternId edits clear the stored fingerprint
  (spec: any change resets); example-value edits keep it, and `is_verified` compares it with the current
  export data, so a bounding-box regime flip shows "verify again" (C1).
- **Automatic order:** rows are packages sharing the same bottom edge for the example values, sorted
  bottom-up, then by left edge.
- **Recognition:** luminance + Canny, edge-free regions, outer contour fill >= 0.95 (rejects label pills),
  container removal (cards, pallet outlines), aspect <= 8 (rules, headers), text blocks via hole count,
  proximity grouping (0.6 x short side), contrast against the surrounding for holes, grid split of merged
  regions (yellow), deskew 0.3-5 deg, vector edge snapping. Real samples: 18/18 and 4/4 patterns.
- **Export** runs in the TaskRunner from a snapshot taken when the dialog is confirmed.
- **Performance** (64 packages, offscreen): drag move + repaint about 11 ms, release about 53 ms;
  window start about 450 ms; heavy libraries are loaded on first use only.
- **Fit to pallet** (`domain/fitting.py`, agreed rule F1): drawing hints (KL/KB part of edges flush in the
  drawing, stored per pattern as `hints`, JSON `drawingHints`, not exported) must hold within one grid step;
  KL >= KB on the grid (Options, 10 mm), pattern valid; fit = 2 x overhang + unused edge; within the tolerance
  (Options, 25 mm) the roundest size wins (x100 > x50 > x10), then less overhang, then more area. Integer
  evaluation in 1/16 mm: 4-15 ms per pattern, so it runs on the GUI thread. Unreachable hints -> fallback
  without them, reported.
- **Excel Patterns sheet** got Width, Height (outline formulas) and ValidWhile (validity conditions), F7.
- **Example values** form a draft when only the pair is inconsistent (KL < KB); applied as one step once valid.
- **Renamed to LayerForge** (G2): package `layerforge`, project files `*.layerforge.json` (old
  `*.layerpattern.json` / format "layerpattern-project" still open), registry `LayerForge\LayerForge`
  (old key copied once), TIA "Generator: LayerForge <version>" while the exchange format name stays
  `LayerPattern-TIA 1` so older DBs keep importing; Siemens names unchanged.
- **Dialogs** are frameless `HaloDialog` / `HaloMessageBox` from QtControlsPyRS (G6); file dialogs stay native.
- **Build** (G3-G5): AUTOBUILD.py, PyInstaller program folder, version from git tags, `--selftest`.
- **Corner reference, pattern names, no placement order** (2026-11-20, for the universal PLC project V4):
  - Coefficients are measured from the lower-left outline corner. Validity conditions only concern the left
    and bottom edges; the PLC computes the outline (and centres the layer on the pallet) itself. Positions
    are never negative, single coefficients can be (EU13: Y = -0.5*KL + 2*KB + D).
  - Every pattern has a name (required, unique ignoring case, <= 16 characters, letters, digits, space and
    `- _ . / + #`), exported as `PatternIndex[].PatternName : String[16]` (not `Name`: NAME is an SCL block attribute keyword). The MFC sends the name, the PLC searches
    it. The name is part of the fingerprint; renaming drops verification.
  - The placement order is computed by the PLC (it depends on where the pallet stands relative to the pickup
    point). The editor shows no package numbers, the sequence panel, Auto Order and Click Order are gone,
    Excel has no Sequence column. Export order inside a pattern = automatic order (rows bottom-up, left to
    right); duplicates are compared in the centre frame (symmetric for mirroring).
  - Format line stays `LayerPattern-TIA 1`; DBs without names (all earlier exports, centre reference) are
    refused on import instead of being read shifted.
  - Editor: the pallet stays centred under the pattern; the origin mark sits on the reference corner and the
    X/Y legs of the selected package start there. PDF tab: *Select all* / *Select none* above the proposals.
