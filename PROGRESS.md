# LayerPattern Tool – Progress Log

Read this first when resuming. Newest entries at the top of "Log".
Design: `doc/DESIGN.md`. Requirements: `../Claude_Code_Prompt_Layerpattern_Tool.txt`.

## Current state

- Phase: **all four phases done** (134 tests green). Waiting for user feedback and a TIA V21 import test. Design approved 2026-11-18 (all D1–D21 as recommended, D20 = set A).
- Phase 0 done: library extended (uncommitted in the library repo – the user commits).

## Next steps

1. User: try the tool (F5 in VS Code), import the generated TIA sources into V21.
2. Then: fix whatever the hands-on test shows.

### Phase 2 plan
- application/undo.py (snapshot undo stack, Qt-free) + tests
- domain/snapping.py (relation catalogue, candidates, resolve; D13/D14) + tests
- presentation: theme (dark/light Fusion palette, dark title bar), icons (inline SVG, black, tinted by HaloCommandBar),
  settings (QSettings registry), session (ProjectSession QObject: project, path, modified, undo, validation cache),
  main_window (HaloCommandBar + HaloTabWidget [Start, Editor, PDF, Help] + StatusBar), start_page,
  pattern_list (delegate, cached previews, hover popup, drag&drop, sort-by-id), editor (view, items, controller,
  dimensions, pallet, guides), properties panel, sequence panel, dialogs (verify, change id, options, unsaved changes)
- run.py + .vscode/launch.json; focused GUI tests (start, export enablement, undo integration)

## Decisions

Status legend: OPEN = asked, waiting for the user; OK = approved; CHANGED = user chose differently.

| # | Topic | Proposal | Status |
| --- | --- | --- | --- |
| D1 | Tool location | `z:\Code\work\kave\LayerPatternTool\` + `git init` (local) | OK |
| D2 | Library extensions | L1 lazy import, L2 HaloCommandBar, L3 StatusBar levels; icons app-local | OK |
| D3 | Theme | dark default, light switchable in Options | OK |
| D4 | PDF backend | pypdfium2 (permissive) instead of PyMuPDF (AGPL) | OK |
| D5 | OpenCV | use installed `opencv-python`, no headless in parallel | OK |
| D6 | GUI architecture | A: immutable document + snapshot undo + thin presenters | OK |
| D7 | Phases | 0 library → 1 domain → 2 shell+editor → 3 PDF → 4 export/help/finish | OK |
| D8 | Coordinates / pallet | X right, Y up; pallet width = X = 1200, length = Y = 800; swap button | OK |
| D9 | Rationalisation | denominators: powers of two ≤ 16; exact decimals, max 4 places | OK |
| D10 | Verified state | fingerprint of exported data | OK |
| D11 | Validity conditions | show inequalities for bbox regime | OK |
| D12 | Clearance | gap < D between facing packages = blocker | OK |
| D13 | Snap catalogue | adjacent+D, flush edges, centres, half-step (lowest priority) | OK |
| D14 | Single rotation (R) | rotate about centre, then re-snap | OK |
| D15 | Recognition | topology-based reconstruction (drawings are not to scale) | OK |
| D16 | KL/KB/D on accept | fields in PDF tab, prefilled from Options defaults | OK |
| D17 | Re-recognition | side-by-side comparison; new / replace (undoable) / discard | OK |
| D18 | PatternIndex | fixed Array[1..99] (deviation from spec) | OK |
| D19 | Whole-DB UDT | none; arrays in DB; type source = 2 stable UDTs | OK |
| D20 | Naming set | A (`UDT_LayerPackage`, `UDT_LayerPatternIndex`, `DB_LayerPatterns`) | OK |
| D21 | File names | `*.layerpattern.json`; `<Project>_Types.udt`, `<Project>_Patterns.db`, `<Project>_Patterns.xlsx` | OK |

## Facts established during inspection (do not re-derive)

- Python 3.13.5; PyQt6 6.11; numpy 2.2.6; opencv-python 4.12 (full); openpyxl 3.1.5; Jinja2 3.1.6; pytest 9.1; pytest-qt 4.5; reportlab 5.0; PySide6 6.9 also installed (never import). PyMuPDF / pypdfium2 not installed.
- pytest-qt picks PySide6 by default here → `qt_api = pyqt6` in pytest.ini.
- `import qt_controls_pyrs` ≈ 280 ms, ≈ 180 ms of it is `requests` via `imgbb`.
- Library path resolves to `\\192.168.178.38\fs\Code\python\QtControlsPyRS\src` (editable install, network share).
- TIA conventions: ASCII, CRLF (V2 imported fine; user confirmed V3 with LF also imports fine in V21), `{ S7_Optimized_Access := 'TRUE' }`, `VERSION`, `NON_RETAIN`, start values after `BEGIN`.
- Kave_Layerpattern.pdf: 4 pages, 1 raster image each (~960 px wide), 18 patterns, package counts 1,2,4,6,8,2,3,9,6,3,7,10,4,5,9,5,5,6. Dark packages = same size rotated (colour must not be used).
- Pallet-formats.pdf: 2 pages, pure vector (Excel, lines as thin rects), 4 patterns, 28/15/22/12 packages, pattern 4 has an internal hole; drawings not to scale.

## Log

### 2026-11-18 – User feedback round 1 (136 tests green)
- Library committed on branch `next` (86fd5be, not pushed). Tool repo: initial commit on master.
- Options dialog had an empty band above the buttons: an empty word-wrapping error label absorbed the
  surplus height. Fix: `dialogs.Message` (hidden while empty) + `SetFixedSize` for all form dialogs.
- Typing KL = 333 while KB was 400 was refused and lost (KL >= KB spans two fields) -> lowering KL and KB
  was impossible in that order. Fix: PropertiesPanel keeps an inconsistent set as a draft (note + Revert),
  the pattern keeps its last valid values, the pair is applied as ONE undo step once consistent.
- Scale question answered: editor is to scale; Pallet-formats p1 pattern 2 draws the same case 1.13 standing
  vs 1.59 lying (schematic). Drawing intent 3*KL = 4*KB + D; KL 320 / KB 240 / D 0 gives 960 x 1200 on the
  stated 1000 x 1200 pallet. Proposed (not built): show such drawn equalities as hints after recognition.

### 2026-11-18 – Phase 4 done (134 tests green, 3 consecutive runs)
- Full offline help (resources/help/index.html, anchors workflow/editor/pdf/... for F1 context).
- Export runs in the TaskRunner (channel "export") from a snapshot; export action disabled while running.
- Pattern list context menu; README.md (run, structure, design rules).
- BUG fixed: PDFium heap corruption with concurrent threads -> global PDFIUM_LOCK in pdf_source.py,
  explicit page/bitmap close; regression test test_concurrent_pdf_access_is_serialised.
- End-to-end GUI test: PDF -> recognize -> accept -> verify -> save/open -> export (3 files) -> import DB.
- Performance: 64-package drag ~11 ms per move incl. repaint, release ~53 ms.

### Acceptance checklist (spec) - status
- [x] starts from VS Code (run.py, .vscode/launch.json)        - [x] new/open/save/save as
- [x] import generated DB as new project                       - [x] multiple PDF imports
- [x] thumbnails, region selection, whole-page + region recognition (real samples 18/18, 4/4)
- [x] proposals accepted without overwriting manual work (compare + explicit Replace)
- [x] patterns add/delete; packages add/move/snap/rotate/duplicate/delete; undo/redo
- [x] sequence by list drag&drop and click order (Esc restores, one undo step)
- [x] symbolic/numeric dimensions live; pallet reference; parameters relative to bbox centre; read-only panel
- [x] validation, verification, duplicates block, mirrors reported, stable IDs with gaps
- [x] Excel 2 sheets + clean formulas; TIA type + DB (set A names, PatternIndex[1..99]); transactional export
- [x] F1/Help tab; long operations cancellable, GUI never blocked; no log files; no packaging changes
- [ ] user: import generated sources in TIA Portal V21 and compile (not possible here)

### 2026-11-18 – Phase 3 done (127 tests green)
- pypdfium2 5.15.2 installed (API v5: obj.get_bounds(), image.get_px_size(), render(crop=(l,b,r,t))).
- infrastructure/pdf_source.py (PdfFile per thread, render page/region, thumbnails, native_scale, vector_edges),
  recognition/detect.py (luminance only, Canny + edge-free regions, filled outer contour fill >= 0.95 rejects
  pills, container removal, max aspect, proximity grouping, contrast-vs-surrounding filter for holes, text-block
  filter by holes, grid split of merged regions, deskew 0.3..5 deg), recognition/pipeline.py (scale choice,
  vector edge snapping, reconstruct + validate -> Proposal with level ok/warning/error).
- presentation/workers.py (TaskRunner: channels, generation counter, CancelToken), pdf_workspace.py (PDF
  dropdown, background thumbnails, page view with region tool and overlays, proposal list with previews and
  check state per entry, accept / accept all valid / discard as one undo step, D17 compare + replace, source
  view, relink, unaccepted-proposal prompt), main window integration (PDF ribbon groups, Source View action).
- Real samples: Kave 18/18 patterns with exact counts, all valid, EU13 identical to hand derivation; Pallet-formats
  28/15 and 27/12 (page 2 is drawn with 27 rectangles although the text says 22). No false proposals.
- Tests: tests/pdf_factory.py (reportlab vector + raster/skew), test_recognition.py, test_workers.py, PDF GUI tests.

### 2026-11-18 – Phase 2 done (111 tests green)
- application/undo.py (snapshot stack, clean marker), application/validator.py (incremental, cached per pattern
  object; export_blockers), domain/snapping.py (catalogue + resolve + snap_package, `feature` for guides).
- presentation: theme.py (dark/light palettes, EditorColors, DWM dark title bar), icons.py (inline SVG),
  settings.py (QSettings registry; tests use IniFormat in tmp), session.py (execute/undo/redo/replace_project,
  message signal), preview.py (cached QImage previews), pattern_list.py (delegate, badges, hover popup owned by
  list, drag&drop, sort-by-id), editor/{items,controller,view}.py (mm scene with Y up, screen-space overlay:
  dimensions, sequence numbers, KL line, centre mark, gaps, guides; modes select/add/place/order),
  properties.py, sequence_panel.py, dialogs.py (unsaved, confirm, details, verify summary, change id,
  dimensions for DB import, options, export dialog), start_page.py, help_tab.py (QTextBrowser, placeholder
  HTML), main_window.py (QAction-driven HaloCommandBar, context groups per tab, editor shortcuts with
  WidgetWithChildrenShortcut), app.py (excepthook -> status bar with details), run.py, .vscode/launch.json.
- Startup ≈ 450 ms offscreen, no heavy module imported at start.
- Lessons: PyQt6 aborts silently on exceptions in paint() unless sys.excepthook is set (app.py does);
  QPainter.drawLine needs QPointF/QLineF for floats; IntField.set_value() emits no signal (lib design);
  GUI tests must answer the unsaved-changes prompt (fixture patches dialogs.ask_unsaved).
- Screenshots via offscreen need QT_QPA_FONTDIR=C:/Windows/Fonts; wait ≥ 600 ms for the tab slide.

### 2026-11-18 – Phase 1 done (85 tests green)
- domain: rational.py (D9 policy, REAL literals), linear.py (LinearForm), model.py (immutable Package/Pattern/
  Project, Dimensions, SourceRef, PdfRef), geometry.py (exact 1/16-mm evaluation, overlap/clearance/neighbours,
  symbolic Extent, relative centres, normalisation, validity conditions D11, overhang), export_model.py (TiaNames
  set A, snapshot, fingerprint D10, is_verified), duplicates.py, validation.py (all blockers + notes incl.
  VERIFICATION_STALE), transform.py (quarter turns), sequence.py (auto order = bottom edge, then left edge),
  operations.py (PatternId rules, rotated copy, dims keep verification, pdf refs), reconstruct.py (D15 topology,
  best-first per axis, adjacent-max rule, estimated/uncertain flags).
- infrastructure: project_store.py (schema v1, fractions as strings, atomic save), excel_export.py (+verify),
  tia_export.py + templates (header/types/db, ASCII CRLF, PatternIndex[1..99]), tia_import.py (own format only).
- application: export_service.py (staging folder, verify, atomic replace with rollback), db_import.py.
- tests: numbers, geometry (EU13 by hand, regime flip), patterns (rotation, duplicates, mirror, ids, snapshot),
  reconstruct (EU13 + 28-case pinwheel from the real PDFs), infrastructure (round trip, golden TIA files in
  tests/golden, Excel, transactional failure), architecture (layer rules). Real PDFs copied to
  tests/fixtures/private (gitignored).

### 2026-11-18 – Phase 0 done
- L1 `qt_controls_pyrs/__init__.py`: lazy `imgbb`/`referencethumb` via PEP 562 → import ≈ 100 ms instead of 280 ms.
- L2 new `qt_controls_pyrs/halocommandbar.py`: `HaloCommandBar`, `HaloCommandGroup`, `HaloToolButton`, `tinted_pixmap`
  (QAction-driven, icons tinted to ButtonText, density 0/1/2 when narrow, NoFocus buttons, checked = accent + underline).
- L3 `StatusBar.show_message(text, level, details)` + signal `details_requested(msg, details)`; `setText` = info.
- Tests: `tests/test_halocommandbar.py`, `tests/test_lazy_import.py`, additions in `tests/test_statusbar.py`. Library suite 428 passed.
- README + CHANGELOG updated (German). Visual check via offscreen render (needs `QT_QPA_FONTDIR=C:/Windows/Fonts` for real glyphs).
- Git: added safe.directory entries for LayerPatternTool (Z: and UNC form), `git init` done.

### 2026-11-18 – Session 1 (cont.)
- User approved all decisions as recommended (D20 = A). Started Phase 0.

### 2026-11-18 – Session 1
- Inspected repository, library, PDFs, TIA conventions, Python environment.
- Wrote `doc/DESIGN.md` (analysis, risks, architecture options, Siemens structure, phases).
- Sent the decision list D1–D21 to the user. Waiting for answers.
