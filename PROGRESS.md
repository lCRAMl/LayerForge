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
| D1 | Tool location | own folder `LayerPatternTool/` (now `LayerForge/`) next to the spec + `git init` | OK |
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
- The library is an editable install from a network share (mapped drive).
- TIA conventions: ASCII, CRLF (V2 imported fine; user confirmed V3 with LF also imports fine in V21), `{ S7_Optimized_Access := 'TRUE' }`, `VERSION`, `NON_RETAIN`, start values after `BEGIN`.
- Kave_Layerpattern.pdf: 4 pages, 1 raster image each (~960 px wide), 18 patterns, package counts 1,2,4,6,8,2,3,9,6,3,7,10,4,5,9,5,5,6. Dark packages = same size rotated (colour must not be used).
- Pallet-formats.pdf: 2 pages, pure vector (Excel, lines as thin rects), 4 patterns, 28/15/22/12 packages, pattern 4 has an internal hole; drawings not to scale.

## Log

### 2026-11-20 – V4 PLC project: sources, Python check chain done ("ALLE PRUEFUNGEN OK")
- LayerForge: UDT field renamed Name -> PatternName (NAME is an SCL block attribute keyword and on the V3
  reserved list); NAME/OK/TITLE/AUTHOR/FAMILY added to the TiaNames reserved set; goldens regenerated,
  160 tests green. Not committed yet (commit 0c2c920 is local only, nothing pushed).
- Build v1.0.0-7-g0c2c920 done before the rename (EXE self-test OK) - must be rebuilt after committing.
- ../V4 created as a copy of V3 (V3 untouched), V3-only files removed. tools/dev_export_from_v3.py builds
  the 18 V3 patterns with LayerForge code (names EU.., PatternId = EU number, verified by script) and
  exports tia/02_LayerForge_{Types.udt,Patterns.db,Patterns.xlsx} - temporary until the user's own export.
- SCL rewritten: 01 types (StandCfg with PB/PL/ZPal/Gap; GantryCfg with StopRight, KLAcross, MaxOverhang,
  LabelCheck, ScanAIsPlus, VarTravel, ZClear, ZTravelMin; LayerPos with Xp/Yp/Wg/Hg/Dist/Rank/App*;
  CoordCache Pos[1..64] = the single max-packages bound; Zt in result/log/diff), 03 DB_GantryCfg with
  Stand[1..10] next to Cfg, 08 FC_LayerCalc (corner coefficients, outline, overhang, centring, outside
  side, rank by pickup distance, in-place cycle sort with duplicate detection 8202, approach per package
  with sweep-box fallback), 09 FC_PackageWP (approach vector, travel height fixed/variable, C for KL across
  the band), 10 name lookup over Array[*], 11 FC_CoordinateCalc (StandCfg[*], pickup point, StackTop),
  12 FC_StandSelect (Array[*]), 13 FB_StandManager (8404 size check, highest-stack region), 14/15/16 test
  bench (Zt column, pallet change only for the completed stand, Calc.StackTop).
- Python: lfdb.py (reads the LayerForge DB), ref_v4.py (independent reference), sim_v4.py (V3 telegrams),
  expect_v4.py, scl_port_v4.py (cycle-accurate, 32-bit Real), gen_v4.py (06/07 DBs, Excel, 7 watch lists,
  CRLF), test_v4.py. lint_scl.py: only .udt/.db/.scl, UInt/USInt known.
- Results: test bench 80 rows, 77/1/2/11 like V3 (decisions identical, coordinates new), port = reference
  (max 0.00025 mm in 32 bit), Rechner 77/77, settings (fixed ZMax, stop right, KL across, no LabelCheck,
  8404), 200 random plants x 120 telegrams in 32 and 64 bit: 0 deviations; lint 0 findings.
- Test data: approach on the line 72, only Y 4, only X 1; variable travel height 1000-1144 mm (ZTravelMin
  start value lowered to 900 so the variable part is exercised).
- Next: V4 docs (Einstiegsdoku in template look via md2docx, chapters settings / MFC interface / travel
  height / guide for the LayerForge export), CHANGELOG, CLAUDE.md; LayerForge commit + rebuild + push.

### 2026-11-20 – LayerForge step done (160 tests green, source self-test OK)
- Corner reference: geometry.corner_relative() for the export, centre_relative() only for duplicates and
  mirror detection; validity conditions left/bottom only; package_rows() uses the automatic order.
- Pattern name: Pattern.name, ops.set_name / add_pattern(name=) with one checker, validation NAME_MISSING /
  NAME_INVALID / DUPLICATE_NAME (check_pattern(require_name=False) for recognition and Fit to pallet),
  fingerprint includes the name, project JSON "name" (optional on read), UDT_LayerPatternIndex.Name
  String[16], DB assignment, import reads names and refuses DBs without (= earlier exports), Excel Name column.
- No placement order anywhere: sequence panel, Auto Order, Click Order, Finish Order, ORDER mode, sequence
  numbers and the Sequence display option removed; Excel without Sequence; verify dialog without Seq;
  validation messages count packages instead of numbering them.
- Editor: origin mark at the lower-left pattern corner, pallet stays centred, X/Y legs from the corner;
  Properties has a Name field; pattern list shows the name and NO NAME / NAME TWICE badges.
- PDF tab: Select all / Select none above the proposal list (Select all includes red proposals).
- Help, README, DESIGN updated; goldens regenerated and checked by hand (EU13 standing package
  Y = -0.5*KL + 2*KB + D: positions are never negative, single coefficients can be - this corrects what I
  told the user in H3, "all coefficients >= 0").
- Found by the self-test path: the self-test pattern needed a name (import refuses nameless DBs).
- Lesson: long Python heredocs through the Bash tool mangle backslashes ("\\n" became a newline in a
  string literal) - write patch scripts with the Write tool instead.

### 2026-11-20 – V4 decisions final, work started
- U6 A approved: travel height = highest stack in the cell + carried case height + clearance (min ZTravelMin,
  max ZMax), plus a config switch between fixed ZMax and the variable height; the behaviour must be
  described exactly in the documentation. B (blending) not documented.
- Plan (H14): 1. LayerForge (corner reference, origin mark at the pattern corner with the pallet centred,
  Select all/none in the PDF tab, pattern name, no package numbers/sequence anywhere, import rejects DBs
  that do not match), tests, build. 2. V4. 3. Documentation.
- Decided while implementing: with the corner reference and a PLC that computes the outline itself, the
  conditions that matter for the coefficients are the left/bottom edges only (H1 as approved). The export
  order of packages inside a pattern is the automatic order (rows bottom-up, left to right at the example
  values) and carries no meaning. Validation messages no longer cite package numbers (the editor marks the
  packages concerned). The fingerprint includes the pattern name (the PLC receives it).

### 2026-11-20 – V4 answers round 5 (nothing changed)
- U1-U5 approved (pallet per stand, carton orientation at the band, max packages per layer as one bound,
  telegram Pattern String[16], ScanSide not needed when the label switch is off).
- New: the documentation gets the MFC interface: every telegram field, what it must contain, what it
  causes in the PLC, plus example telegrams.
- U6: the user corrected the earlier statement on travel height: the gantry must travel at ZMax between pickup and place for
  self-protection, which is pointless when the lift is as long as the horizontal way; no extra check
  function wanted. Checked (scratch path_cross.py): in the V3 layout the straight line pickup -> place
  crosses a neighbouring pallet for 8 of 10 stands (1->2, 2->3, 4->3, 5->4, 6->7, 7->8, 9->8, 10->9), so
  looking only at the target stack is unsafe. Proposal sent: travel height = highest stack in the cell +
  carried case height + clearance (at least a fixed minimum, at most ZMax), one MAX over the stands per
  package; option: blending in the motion control.

### 2026-11-20 – V4 answers round 4, review for universal settings (nothing changed)
- H15 stop side setting yes; H8.2 keep the check with a maximum overhang per side (start 50 mm); H16 (a)
  stand count only in the three DBs, blocks take Array[*].
- H7.6b: LayerForge must not show package numbers at all (they would look like a placement order): no
  sequence overlay, no sequence panel / order mode, Excel loses the Sequence column (GlobalPackageIndex
  stays for the DB mapping), DB comment says the array order is not the placement order.
- Review of all V3 sources for values that must become settings (user request). Proposed: pallet size and
  height per stand (V3 global PB/PL/ZPal), carton orientation at the pickup (V3 assumes KL along the band),
  max packages per layer as one bound (64 = LayerForge default), telegram Pattern String[8] -> String[16],
  ScanSide/NoRead handling when the label switch is off. Already settings: XStop, YBand, ZBand, ZMax, SApp,
  DzApp, ZSafe, DimTol, ScanAIsPlusY, CSign, per stand Fx/Fy/Theta/Gap. Assumptions that are functions, not
  values (to document as limits): same pattern on every layer, no interlayer sheets, one package per pick
  gripped at its centre, travel at fixed ZMax, nearest free stand per new order, Theta 0/90/180/270.
  Test bench arrays (120 telegrams) follow the generator.

### 2026-11-20 – V4 answers round 3 (nothing changed)
- H7.5 a (simple rule: farthest from the pickup first, line approach, per-package fallback), H7.6 b (no
  placement order in LayerForge any more: automatic package numbering only, sequence tools removed),
  H8.3 switch + a documentation chapter listing everything that must / can be set, H8.4 and H9.1 as proposed.
- New from the user: the pickup point moves along a horizontal line between the pallet rows from project
  to project. Simulation rerun with XStop 0/1500/4400/6500 and YBand 1900/2700: fallback 1.2-2.5 %, never
  vertical -> no problem; the pickup is already configuration (XStop, YBand). Open: stop side (V3: pickup =
  XStop + KL/2, carton's left edge at the stop).
- H8.2: user wants overhang allowed and asks whether the PLC fit check is needed at all (pattern approved in
  LayerForge). Answer: LayerForge approves the pattern with example sizes only; the real carton size comes
  per order from the MFC, so only the PLC can check it. Proposal: keep it (two comparisons, the outline is
  computed anyway) with a configurable maximum overhang per side.
- Also found: the stand count 10 is hard-coded in UDTs, DBs and loops of V3 -> question how V4 makes it
  universal (bound in the DBs + Array[*]/UPPER_BOUND in the blocks recommended).

### 2026-11-20 – V4 answers round 2, order/approach proposal sent (nothing changed)
- H3: no format bump; the import simply rejects DBs that do not match the V4 structure. Exported values stay
  as they are (BaseOrientation + 6 coefficients, corner reference) - no width/height/bounding box. The only
  addition is the pattern name (H6 approved: name field in LayerForge, exported to PatternIndex[].Name).
  -> The PLC computes the outline itself (MIN/MAX inside the loop that computes the centres anyway).
- H10 (02_LayerForge) and H13 (cover: only what describes V4; version history stays) approved.
- H7 clarified by the user: approach on the straight line pickup -> place point (true direction per package,
  not V3's fixed 45 deg per stand), shortest paths, detours only when a case is in the way; pickup lies
  between an upper and a lower pallet row, never approach from beyond the outer row. Order must therefore
  depend on where the pallet stands -> the user asks whether to compute the order in the PLC.
- Simulation (scratch, V3 patterns, V3 stand layout without margins, D 0/5/20, KL 200-800, KB 150-KL,
  70870 layers, 249060 packages), rule "farthest from the pickup first", approach SApp 50 on the line,
  path test = moving box against placed boxes: 97.9 % on the line, 2.1 % need a fallback (drop one
  component: 3228 x straight on, 2071 along x), never vertical. Fallbacks: stands 3/8 in front of the pickup
  (all patterns, unavoidable: row neighbours want to come from each other's side) and mixed patterns with
  a rotated block on all stands. A precedence order ("i before j if j lies in i's path", n^3) removes the
  mixed-pattern cases; only stands 3/8 remain. Detour of a fallback <= 50*(1-cos 45) ~ 15 mm.
- Proposal sent: order + approach computed in the PLC once per order (cached), LayerForge sequence becomes a
  plain package number; open: simple rule vs precedence order, LayerForge numbering kept/renamed or removed,
  H8.2-8.4 and H9.1 still unanswered.

### 2026-11-20 – V4 answers round 1, follow-up questions sent (nothing changed)
- Answers: H1 corner reference yes; H2 (b) pallet stays centred in the editor, origin mark moves to the pattern
  corner; H4, H5, H11, H12 as proposed; H9 the user builds the pattern project and exports it themselves -> write
  a short guide; H10 no project name in file names; H13 leave out everything that does not describe V4; H14 order
  as proposed, but only after the open points are settled.
- Corrections by the user: no backward compatibility needed (development project), LayerForge export and TIA
  must simply be consistent; V4 must be universal (no project pattern names like EU.., any number of patterns,
  no "dark" rule); approach direction chosen from pickup point towards the place point; layer centred on the
  pallet, margins TX/TY removed, Align removed, D = Gap; PLC computes as little as possible; V4 need NOT
  reproduce V3 (V3 was only the base and must stay untouched).
- Facts for the follow-up: Pattern has no name field today (only PatternId); export already knows width/height
  as LinearForm (Excel only). With corner reference + centring, the PLC needs W/H -> right/top validity
  conditions stay relevant (correction of the H1 claim). Computed approach (sign of pickup - pallet centre) equals
  the V3 config for 9 of 10 stands; stands 3/8 sit in front of the pickup (X 2900-3700 vs 3000 + KL/2), stand 3
  flips to -X. Target is S7-1500 -> ARRAY[*] parameters make V4 independent of the export size.
- Follow-up questions sent: H3 (explained: format 2, old DBs rejected, W/H added), H6 (pattern name in
  LayerForge exported to PatternIndex[].Name vs MFC sends PatternId), H7.1-7.3 (approach per stand from pickup to
  pallet centre, generalised rank rule with sx/sy, LayerForge sequence = PkgNo only), H8.1-8.4 (export W/H, fit
  check without overhang, barcode-outside logic behind a switch, own V4 expectations), H9.1 (temporary export
  from the V3 geometry until the user's own), H10 base name 02_LayerForge, H13 interpretation.

### 2026-11-20 – Request: pallet reference lower-left, Select all/none, V4 of the PLC project (questions H1-H14 sent, nothing changed)
- Request: (1) reference point lower-left corner instead of pattern centre, (2) PDF tab proposals Select all /
  Select none, (3) new folder ../V4 = V3 PLC project (gantry palletizer, TIA V21 SCL) adapted to LayerForge data,
  V3 untouched, (4) V4 documentation in the look of ../IC-Contractor-Scope-of-Work-11492_WORD_DE.docx.
- Findings: geometry.relative_centers() is the single place of the export reference; packages are stored
  normalized to the lower-left corner already. Corner reference needs only left/bottom edges for validity.
- V3: DB_PatternData (old coefficient model: Rot 1 = KL along Y, Dark, kx*/ky* = package corner, km* = Align
  shift), FC_LayerCalc centres the layer in the net area (TX/TY), ranks itself (dark first, back->front,
  against approach sx), all 10 stands Align 0, Gap 0, pallet PB 800 (X) x PL 1200 (Y). MFC sends pattern
  names 'EU01'..'EU96'. Checked: V3 ranks without the dark rule are identical for all 18 patterns, both sx,
  6 sizes (dark packages always lie at the back).
- Template: Smartsheet scope-of-work layout, Century Gothic, H1 caps 14 pt #595959, H2 caps 12 pt #44546A,
  table head #222A35/#323E4F, cells #D5DCE4/#EAEEF3, cover page, version history table, TOC, footer
  "Seite X von Y", US Letter. Rendered via Word COM to scratch for inspection.

### 2026-11-19 – Public README, GPL-3.0, no local paths
- README.md rewritten for the public repo: what the tool does, requirements, step-by-step setup (clone, venv,
  QtControlsPyRS from GitHub branch next, requirements.txt, run, tests), AUTOBUILD steps, layout, design rules.
  No local paths. requirements.txt: local path comment replaced by the GitHub install line.
- QtControlsPyRS: main was 0.2.0, LayerForge needs 0.4.0 (HaloDialog/HaloCommandBar). User approved:
  next fast-forwarded into main (5122ddb); README installs `git+https://github.com/lCRAMl/QtControlsPyRS.git`.
- Verified in a fresh public clone + fresh py3.13 venv on C: (PyQt6 6.12.1, numpy 2.5.5, opencv-headless 5.1,
  PyInstaller 6.22.3): source self-test OK, 150 passed / 2 skipped (private PDFs), AUTOBUILD + EXE self-test OK.
  The clone build retargets Start Menu/Programs/LayerForge.lnk -> pointed back to the real build afterwards.
- User approved: local paths, drive letters and the share IP removed from CLAUDE.md, PROGRESS.md and
  doc/DESIGN.md (they stay in the git history; no rewrite). Machine-specific facts moved to Claude's memory.
- LICENSE: GPL-3.0 (gnu.org text), chosen because of PyQt6. README has a License section.

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
- User renamed the folder to LayerForge; git safe.directory entries added for the mapped-drive and the UNC form
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
- Source: AUTOBUILD.py of the user's APIImageGenerator project (+ core/build_info.py, build_version.py pattern):
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
- TRXing (another project of the user) solves the inverse problem (given package -> arrangement); not reusable here.
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
