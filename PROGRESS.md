# LayerForge (formerly LayerPattern Tool) – Progress Log

Read this first when resuming. Newest entries at the top of "Log".
Design: `doc/DESIGN.md`. Requirements: `../Claude_Code_Prompt_Layerpattern_Tool.txt`.

## Current state

- Phase: **all four phases done + Fit to pallet + packaging** (152 tests green). Waiting for user feedback and a TIA V21 import test. Design approved 2026-11-18 (all D1–D21 as recommended, D20 = set A).
- Phase 0 done: library extended (uncommitted in the library repo – the user commits).

## Next steps

1. User: try the tool (F5 in VS Code), import the generated TIA sources into V21.
2. Then: fix whatever the hands-on test shows.
3. Everything committed (8c4d700).

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

### 2026-11-18 – Properties buttons, new icon, other programs' builds
- Properties "Example values": Swap pallet now sits left, directly above Fit to pallet, same width
  (small grid: Swap / Fit + Alternatives); pending note and Revert moved up to rows 5/6.
- Icon redrawn: only the layer pattern (3 standing + 2 lying of the same case, 18.67 x 29.5 in a 64 grid,
  gap 3), filling the icon, transparent background; star, pallet and tile background removed. ICO/PNG
  regenerated with tools/make_icon.py. Crisp from 24 px, slightly soft at 16 px.
- Other programs (user request, not committed there): APIImageGenerator, LeechForum (Forum Image Downloader)
  and PicPromptEditor AUTOBUILD.py now write a stable <App>.lnk into Start Menu/Programs and run the same
  Start-tile check. Stable ForumImageDownloader.lnk and PicPromptEditor.lnk created by hand pointing at the
  current EXEs; APIImageGenerator.lnk already existed. TRXing has no shortcut logic (unchanged).

### 2026-11-18 – Start tile, centred version line
- User renamed the folder to z:/Code/work/kave/LayerForge; safe.directory added for Z: and %(prefix)/// UNC form
  (the earlier attempt never ran: it was chained after the failed mv).
- The Start shortcut pointed into the old folder. The user's other tiles reference versioned .lnk files that
  Windows creates when the EXE itself is pinned - they go stale with every build.
- AUTOBUILD: stable Start Menu/Programs/LayerForge.lnk retargeted on every build. Programmatic "Pin to Start"
  is refused by Windows 10 (shell verb DoIt -> E_ACCESSDENIED; only Explorer may pin), so check_start_tile()
  only verifies via Export-StartLayout and prints the one-time manual step. A tile pinned to LayerForge.lnk
  follows every later build.
- Start page: version line centred; title, subtitle and "Recent projects" indented by HaloButton.ROOM and the
  FrameButton list inset by ROOM - RING_ROOM, so all edges line up with the button frames.

### 2026-11-18 – LayerForge: rename, Halo dialogs, AUTOBUILD (152 tests green)
- Decisions G1-G6 approved as recommended (repo by Claude, rename as proposed, program folder, icon, v1.0.0, Halo dialogs).
- Library: new `halodialog.py` (HaloDialog: frameless, own title bar, drag, Esc/Enter; HaloMessageBox:
  kinds info/question/warning/error, keyed buttons, ask(), details), tests, README, CHANGELOG. Lib suite 436.
- Rename: package `layerforge` (git mv), APP_NAME "LayerForge", version from build_version.py ("dev" in
  source), project_store EXTENSION .layerforge.json + legacy, settings LayerForge\LayerForge + migrate_from
  (called in app.py), tia_export.render(generator=...) and goldens with "LayerForge 1.0", help/README/launch.
- The FOLDER rename LayerPatternTool -> LayerForge failed ("Device or resource busy" - VS Code has files
  open). Must be done with VS Code closed; then add safe.directory entries for the new path (already added).
- Dialogs: all QMessageBox uses replaced (dialogs.ask_unsaved/confirm/show_details, PDF proposals prompt),
  own dialogs subclass HaloDialog (content on self.body, _fit_to_content(dialog)).
- Icon: layerforge/resources/icons/layerforge.svg -> tools/make_icon.py -> .ico (9 sizes) + 256 png;
  icons.app_icon() for the window. presentation/selftest.py + `--selftest [report]` in app.py.
- AUTOBUILD.py adapted (program folder, data files, excludes PySide6 and PIL, self-test, Start-menu shortcut).
- Pushed: https://github.com/lCRAMl/LayerForge (branch main, tag v1.0.0 on d08d345).
- Library pushed: QtControlsPyRS branch next, 5122ddb (HaloDialog/HaloMessageBox; 86fd5be before).
- Build v1.0.0-0-gd08d345: output/LayerForge_v1.0.0-0-gd08d345/ 184 MB (pruned ffmpeg video DLL and
  opengl32sw.dll, 47 MB), self-test of the EXE all OK, start incl. self-test ~1.1 s from the network drive.
- Build lessons: build in place (moving a fresh build on Z: fails, scanner holds DLLs); stdout reconfigured to
  UTF-8 for the emoji lines; never leave a shell inside output/ (Windows cannot delete a cwd; a failed
  `cd ... && rm` does not move the session shell).

### 2026-11-18 – Request: AUTOBUILD, repo LayerForge, rename, lib-style dialogs (questions sent, nothing changed)
- Source: Z:/Code/python/APIImageGenerator/AUTOBUILD.py (+ core/build_info.py, build_version.py pattern):
  PyInstaller --onefile --windowed, version from `git describe --tags --long`, Start-menu shortcut via pywin32.
  PyInstaller 6.22.2 + pywin32 installed. No icon exists for this tool yet.
- GitHub https://github.com/lCRAMl/LayerForge.git exists and is empty (ls-remote: no refs).
- Questions G1-G6: who sets up the remote/pushes; rename scope (package, folder, extension, registry, TIA
  generator vs format name); onefile vs onedir (start time); icon; version tag; frameless Halo dialogs
  (HaloDialog/HaloMessageBox in the library vs app-local; file dialogs stay native).

### 2026-11-18 – Fit to pallet implemented (150 tests green)
- domain/cancel.py (Cancelled moved out of infrastructure), reconstruct.drawing_hints -> Reconstruction.hints,
  Pattern.hints (+ JSON drawingHints, optional), operations add/replace/rotated_copy pass hints,
  geometry.primitive(positive=) and Condition.text(times, ge), domain/fitting.py (rule as agreed).
- UI: Properties "Fit to pallet" + "Alternatives" menu (one undo step each), "Drawing proportions" line in the
  status block; PDF tab "Fit to pallet" for the selected proposal (fills KL/KB, shows hints in details);
  Options group "Fit to pallet" (grid 5/10/25/50, tolerance mm); settings fit_step/fit_band.
- Excel Patterns sheet: Width, Height, ValidWhile.
- Help rewritten: contents by topic, Where/Requires/Result per function, Fit to pallet, keys, colours, FAQ.
- Tests: tests/test_fitting.py (rule, roundness band, fallback, hints from the user's VMF screenshot), hint
  persistence, GUI fit in editor and PDF tab, updated Excel test.

### 2026-11-18 – Fit to pallet: answers
- F1 (user): overhang allowed; prefer "round" numbers (300 > 305 > 307); then least overhang and most area;
  flush stays flush. F2 10 mm, F3 D fixed, F4 both places, F5 persist drawing hints, F6 manual = fit only,
  F7 add Width/Height/ValidWhile to the Excel Patterns sheet.
- Proposed rule (prototype): flush hints = KL/KB part of drawn coincidences (|g| <= 1 step); fit deviation =
  2 x overhang + unused edge (mm, width + height); candidates within best + 25 mm; rank roundness
  (x100=3, x50=2, x10=1, KL+KB) > less overhang > more area. Results: VMF 320x240, EU04 400x400, EU09 400x260.
  Real implementation needs integer evaluation (prototype 2.5-3.5 s for patterns without hints).

### 2026-11-18 – Proposal "Fit to pallet" (nothing implemented yet, user asked to be asked first)
- TRXing (Z:/Code/python/TRXing) solves the inverse problem (given package -> arrangement); not reusable here.
- Throw-away prototype (scratch only): brute force over KL >= KB on a 10 mm grid, D fixed, pattern must fit the
  pallet, edges flush in the drawing must stay flush, maximise covered area, validity check on the best ones.
  VMF 15 cases (1000 x 1200, D 0) -> 320 x 240, 96 %; pinwheel 28 cases -> 240 x 160, 90 %; 0.3-0.6 s.
- Prototype lessons: touching cells must not yield a "D = 0" equality; outline drawings (gap 0) do not show
  where D goes, so equalities differing only in D need to be merged / tolerated by their D term.
- Open questions F1-F7 sent (criterion, grid, D fixed, where in the GUI, persist drawing hints, manual patterns,
  Excel Patterns sheet extra columns Width/Height/ValidWhile).

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
