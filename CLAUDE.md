# LayerForge (formerly LayerPattern Tool) – notes for Claude Code

- Resume from `PROGRESS.md` (state, decisions, next steps). Update it after every work step.
- Requirements: `../Claude_Code_Prompt_Layerpattern_Tool.txt` (this spec replaces the V1–V3 parameter model; never reuse old field/variable names).
- Design: `doc/DESIGN.md`.
- Talk to the user in German (Du). Before building: plan + questions, each with a recommendation ("passt" is a valid answer).
- Tool code, UI, comments, docs: English. Comments only where they add meaning, no filler.
- Library QtControlsPyRS (https://github.com/lCRAMl/QtControlsPyRS; local checkout path in Claude's memory): German comments/README; extensions follow its style and get tests + CHANGELOG entry.
- Never import PySide6. pytest must run with `qt_api = pyqt6`.
- Domain layer must not import PyQt6, OpenCV, the PDF backend, openpyxl or Jinja2.
- No log files. Packaging is in scope since 2026-11-18 (user request): `python AUTOBUILD.py`
  builds the program folder, self-tests it, retargets Start Menu\Programs\LayerForge.lnk and
  checks the Start tile (Windows refuses programmatic pinning; the user pins once).
- Public repository (GPL-3.0): never commit local paths, drive letters, network addresses or user names.
  Machine-specific facts belong in Claude's memory, not in the repo.
