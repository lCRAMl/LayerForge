"""Focused GUI checks: start-up, core state wiring, undo integration, export enablement."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from helpers import KB, KL, D, H, eu13, grid  # noqa: E402
from PyQt6.QtCore import QPoint, QPointF, QSettings, Qt  # noqa: E402

from layerpattern.domain import operations as ops  # noqa: E402
from layerpattern.domain import validation as v  # noqa: E402
from layerpattern.domain.export_model import is_verified  # noqa: E402
from layerpattern.domain.model import Dimensions, Project  # noqa: E402
from layerpattern.presentation import dialogs  # noqa: E402
from layerpattern.presentation.editor.controller import ADD, ORDER, SELECT  # noqa: E402
from layerpattern.presentation.settings import AppSettings  # noqa: E402


@pytest.fixture
def window(qtbot, tmp_path, qapp, monkeypatch):
    from layerpattern.presentation.main_window import MainWindow
    from layerpattern.presentation.theme import apply_theme

    # Closing a modified project asks; a modal box would block the offscreen test run.
    monkeypatch.setattr(dialogs, "ask_unsaved", lambda *_a: "discard")
    settings = AppSettings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    apply_theme(qapp, "dark")
    win = MainWindow(settings)
    win.resize(1400, 860)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    return win


def load(win, qtbot, *patterns):
    project = Project(name="Test")
    uids = []
    for packages, pid in patterns:
        project, uid = ops.add_pattern(project, packages, pattern_id=pid)
        uids.append(uid)
    win._start_project(project, None, "loaded")
    qtbot.wait(400)                        # tab slide + first fit
    return uids


def centre(win, index):
    return win.ctrl.items[index].sceneBoundingRect().center()


def test_starts_with_start_page_and_locked_tabs(window):
    assert window.tabs.currentWidget() is window.start
    assert not window.tabs.isTabEnabled(1)
    assert not window.act_export.isEnabled()
    assert window.windowTitle() == "LayerPattern Tool"


def test_new_project_new_pattern_enters_add_tool(window, qtbot):
    window.new_project()
    window.new_pattern()
    qtbot.wait(50)
    assert window.tabs.currentWidget() is window.editor_page
    assert window.ctrl.mode == ADD and window.act_add.isChecked()
    # First click: the first package goes to the origin, wherever the cursor is.
    window.ctrl.press(QPointF(5000, 5000), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    assert len(window.session.current_pattern().packages) == 1
    # Second click next to it snaps to "right of #1".
    first = centre(window, 0)
    window.ctrl.move(QPointF(first.x() + 625, first.y() + 5))
    window.ctrl.press(QPointF(first.x() + 625, first.y() + 5), Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier)
    pattern = window.session.current_pattern()
    assert len(pattern.packages) == 2
    assert window.session.report(pattern.uid).valid
    window.ctrl.cancel()
    assert window.ctrl.mode == SELECT


def test_drag_snaps_and_is_one_undo_step(window, qtbot):
    load(window, qtbot, (grid(2, 1), 1))
    before = window.session.project
    a = centre(window, 1)
    # Drag package #2 on top of #1 (above it, slightly off).
    window.ctrl.press(a, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    target = QPointF(centre(window, 0).x() + 7, centre(window, 0).y() + 420 - 6)
    window.ctrl.move(QPointF(a.x() + 30, a.y() + 30))
    window.ctrl.move(target)
    window.ctrl.release(target)
    pattern = window.session.current_pattern()
    assert window.session.project is not before
    p1, p2 = pattern.packages
    assert p2.y - p1.y == KB + D and (p2.x - p1.x).is_zero()
    assert window.session.report(pattern.uid).valid
    window.session.undo_step()
    assert window.session.project is before
    window.session.redo_step()
    assert window.session.current_pattern().packages == pattern.packages


def test_drag_through_the_view_widget(window, qtbot):
    load(window, qtbot, (grid(2, 1), 1))
    view = window.view
    start = view.mapFromScene(centre(window, 1))
    end = view.mapFromScene(QPointF(centre(window, 0).x(), centre(window, 0).y() + 420))
    qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    for k in range(1, 6):
        pos = start + (end - start) * k / 5
        qtbot.mouseMove(view.viewport(), pos=QPoint(int(pos.x()), int(pos.y())))
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    p1, p2 = window.session.current_pattern().packages
    assert p2.y - p1.y == KB + D


def test_rotate_delete_duplicate_and_undo(window, qtbot):
    load(window, qtbot, (grid(3, 1), 1))
    ctrl = window.ctrl
    ctrl._select([2])
    window.act_rotate.trigger()
    pattern = window.session.current_pattern()
    assert pattern.packages[2].orientation == 90
    assert window.session.report(pattern.uid).valid          # re-snapped, not floating
    ctrl._select([1])
    window.act_delete.trigger()
    assert len(window.session.current_pattern().packages) == 2
    ctrl._select([0])
    window.act_duplicate.trigger()
    assert ctrl.mode == "place"
    ctrl.press(QPointF(centre(window, 0).x(), centre(window, 0).y() + 450), Qt.MouseButton.LeftButton,
               Qt.KeyboardModifier.NoModifier)
    assert len(window.session.current_pattern().packages) == 3
    for _ in range(3):
        window.act_undo.trigger()
    assert len(window.session.current_pattern().packages) == 3
    assert window.session.current_pattern().packages == grid(3, 1)


def test_click_order_and_escape(window, qtbot):
    load(window, qtbot, (grid(3, 1), 1))
    ctrl = window.ctrl
    original = window.session.current_pattern().packages
    window.act_click_order.trigger()
    assert ctrl.mode == ORDER
    ctrl.press(centre(window, 2), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.act_cancel.trigger()                          # Esc restores
    assert window.session.current_pattern().packages == original
    window.act_click_order.trigger()
    for index in (2, 1, 0):
        ctrl.press(centre(window, index), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    assert window.session.current_pattern().packages == tuple(reversed(original))
    window.act_undo.trigger()                            # one undo step for the whole click order
    assert window.session.current_pattern().packages == original


def test_sequence_list_drag_and_drop(window, qtbot):
    load(window, qtbot, (grid(3, 1), 1))
    original = window.session.current_pattern().packages
    window.ctrl.move_in_sequence(0, 2)
    assert window.session.current_pattern().packages == (original[1], original[2], original[0])
    assert window.sequence.list.count() == 3


def test_export_enabled_only_when_all_verified(window, qtbot, monkeypatch):
    a, b = load(window, qtbot, (grid(2, 1), 1), (eu13(), 2))
    assert not window.act_export.isEnabled()
    monkeypatch.setattr(dialogs.VerifyDialog, "exec", lambda self: dialogs.QDialog.DialogCode.Accepted)
    window.session.set_current(a)
    window.act_verify.trigger()
    assert not window.act_export.isEnabled()
    window.session.set_current(b)
    window.act_verify.trigger()
    assert window.act_export.isEnabled()
    # Moving a package resets that pattern's verification and locks export again.
    window.ctrl._select([0])
    window.act_rotate.trigger()
    assert not window.act_export.isEnabled()


def test_example_values_keep_verification(window, qtbot, monkeypatch):
    (uid,) = load(window, qtbot, (grid(2, 2), 1))
    monkeypatch.setattr(dialogs.VerifyDialog, "exec", lambda self: dialogs.QDialog.DialogCode.Accepted)
    window.act_verify.trigger()
    field = window.properties.fields["kl"]
    field.spin.setValue(700)                 # like a committed user entry
    assert window.session.current_pattern().dims.kl == 700
    assert is_verified(window.session.current_pattern())
    field.spin.setValue(300)                 # smaller than KB: not applied, kept as a draft
    assert window.session.current_pattern().dims.kl == 700
    assert window.status.level() == "warning"
    assert not window.properties.pending.isHidden()
    window.properties.revert.click()         # Revert restores the last valid value
    assert field.value() == 700 and window.properties.pending.isHidden()


def test_unsaved_changes_are_asked_for(window, qtbot, monkeypatch):
    load(window, qtbot, (grid(2, 1), 1))
    window.ctrl._select([0])
    window.act_delete.trigger()
    asked = []
    monkeypatch.setattr(dialogs, "ask_unsaved", lambda *_a: asked.append(1) or "cancel")
    window.new_project()
    assert asked and window.session.project.name == "Test"
    monkeypatch.setattr(dialogs, "ask_unsaved", lambda *_a: "discard")
    window.new_project()
    assert window.session.project.name == "Untitled"


def test_overlay_paints_in_all_modes(window, qtbot):
    load(window, qtbot, (eu13(), 1))
    ctrl = window.ctrl
    for name in ("centres", "bbox", "overhang", "numeric"):
        ctrl.set_display(name, True)
    ctrl._select([2])
    window.view.grab()
    ctrl.start_order()
    window.view.grab()
    ctrl.cancel()
    ctrl.start_add()
    ctrl.move(QPointF(0, 0))
    window.view.grab()
    ctrl.cancel()
    window.grab()


def test_invalid_pattern_shows_red_items(window, qtbot):
    isolated = grid(2, 1) + (grid(1, 1)[0].moved(KL * 5, KB * 5),)
    load(window, qtbot, (isolated, 1))
    report = window.session.report(window.session.current_uid)
    assert report.has(v.DISCONNECTED)
    assert window.ctrl.items[2].state == 1
    assert not window.act_verify.isEnabled()


# --- PDF workspace -----------------------------------------------------------

def _import(window, qtbot, pdf_path):
    import os
    ws = window.pdf_workspace
    window.session.execute("Import PDF", lambda p: ops.add_pdf(p, os.path.normpath(str(pdf_path)))[0])
    ws.pdf_id = window.session.project.pdfs[-1].pdf_id
    ws.refresh_pdfs()
    ws._load_pdf()
    qtbot.waitUntil(lambda: ws.thumbs.count() > 0, timeout=5000)
    return ws


def test_pdf_recognize_accept_undo_and_source_view(window, qtbot, tmp_path):
    from pdf_factory import grid as layout, vector_pdf

    pdf = vector_pdf(tmp_path / "two.pdf", layout(60, 120, 3, 2, 80, 50, 4) + layout(380, 520, 2, 1, 50, 80, 4))
    window.new_project()
    ws = _import(window, qtbot, pdf)
    window.tabs.setCurrentWidget(window.pdf_page)
    assert all(g.isVisible() for g in window.pdf_groups)
    ws.recognize_pages()
    assert not ws.act_recognize.isEnabled()                 # busy while running
    qtbot.waitUntil(lambda: len(ws.entries) == 2 and ws.act_recognize.isEnabled(), timeout=10000)
    before = window.session.project
    ws.accept_valid()
    project = window.session.project
    assert len(project.patterns) == 2 and not ws.entries
    assert all(p.source is not None and p.origin == "recognized" for p in project.patterns)
    window.session.undo_step()                              # one command for all proposals
    assert window.session.project is before
    window.session.redo_step()
    window.session.set_current(window.session.project.patterns[0].uid)
    window.tabs.setCurrentWidget(window.editor_page)
    window.act_source_view.trigger()
    assert window.tabs.currentWidget() is window.pdf_page
    assert ws.view.source_rect == window.session.current_pattern().source.rect


def test_region_rerecognition_offers_replace(window, qtbot, tmp_path):
    from pdf_factory import grid as layout, vector_pdf

    pdf = vector_pdf(tmp_path / "one.pdf", layout(100, 150, 2, 2, 80, 50, 4))
    window.new_project()
    ws = _import(window, qtbot, pdf)
    ws.recognize_pages()
    qtbot.waitUntil(lambda: len(ws.entries) == 1 and ws.act_recognize.isEnabled(), timeout=10000)
    ws.accept_valid()
    uid = window.session.project.patterns[0].uid
    # Edit the accepted pattern, then recognize the same area again.
    window.session.execute("edit", lambda p: ops.set_packages(p, uid, grid(1, 1)))
    ws.recognize_region((80, 130, 300, 280))
    qtbot.waitUntil(lambda: len(ws.entries) == 1 and ws.act_recognize.isEnabled(), timeout=10000)
    ws.select_entry(ws.entries[0].key)
    assert not ws.compare.isHidden()
    assert window.session.current_pattern().packages == grid(1, 1)       # nothing overwritten
    ws.replace_selected()
    assert len(window.session.project.pattern(uid).packages) == 4


def test_unaccepted_proposals_are_asked_for(window, qtbot, tmp_path, monkeypatch):
    from pdf_factory import grid as layout, vector_pdf
    from PyQt6.QtWidgets import QMessageBox

    pdf = vector_pdf(tmp_path / "p.pdf", layout(100, 150, 2, 1, 80, 50, 4))
    window.new_project()
    ws = _import(window, qtbot, pdf)
    ws.recognize_pages()
    qtbot.waitUntil(lambda: len(ws.entries) == 1 and ws.act_recognize.isEnabled(), timeout=10000)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Cancel)
    window.new_project()
    assert ws.entries                                         # kept: user cancelled
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard)
    window.new_project()
    assert not ws.entries


def test_missing_pdf_keeps_patterns_editable(window, qtbot, tmp_path):
    from layerpattern.domain.model import SourceRef

    window.new_project()
    project, pdf_id = ops.add_pdf(window.session.project, str(tmp_path / "gone.pdf"))
    project, uid = ops.add_pattern(project, grid(2, 1), source=SourceRef(pdf_id, 0, (0, 0, 10, 10)))
    window._start_project(project, None, "x")
    qtbot.wait(300)
    assert not window.pdf_workspace.show_source(project.pattern(uid))
    assert window.status.level() == "warning"
    window.ctrl._select([0])
    window.act_rotate.trigger()
    assert window.session.current_pattern().packages[0].orientation == 90


def test_full_workflow_pdf_to_tia_and_back(window, qtbot, tmp_path, monkeypatch):
    """New project -> PDF -> recognize -> accept -> verify -> save/open -> export -> import DB."""
    from pdf_factory import grid as layout, vector_pdf
    from PyQt6.QtWidgets import QFileDialog

    from layerpattern.application.export_service import ExportRequest
    from layerpattern.infrastructure import tia_import

    pdf = vector_pdf(tmp_path / "plan.pdf", layout(60, 120, 3, 2, 80, 50, 4) + layout(380, 520, 2, 1, 50, 80, 4))
    window.new_project()
    ws = _import(window, qtbot, pdf)
    ws.recognize_pages()
    qtbot.waitUntil(lambda: len(ws.entries) == 2 and ws.act_recognize.isEnabled(), timeout=10000)
    ws.accept_valid()

    monkeypatch.setattr(dialogs.VerifyDialog, "exec", lambda self: dialogs.QDialog.DialogCode.Accepted)
    for pattern in window.session.project.patterns:
        window.session.set_current(pattern.uid)
        window.act_verify.trigger()
    assert window.act_export.isEnabled()

    target = tmp_path / "Plan.layerpattern.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    assert window.save_as()
    assert not window.session.is_modified() and window.session.project.name == "Plan"
    saved = window.session.project
    window._open(target)
    assert window.session.project == saved

    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(dialogs.ExportDialog, "exec", lambda self: dialogs.QDialog.DialogCode.Accepted)
    monkeypatch.setattr(dialogs.ExportDialog, "request", lambda self: ExportRequest(out, "Plan"))
    window.export()
    qtbot.waitUntil(lambda: len(list(out.iterdir())) == 3, timeout=10000)
    assert sorted(p.name for p in out.iterdir()) == ["Plan_Patterns.db", "Plan_Patterns.xlsx", "Plan_Types.udt"]

    imported = tia_import.read(out / "Plan_Patterns.db")
    assert [p.pattern_id for p in imported.patterns] == sorted(p.pattern_id for p in saved.patterns)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(out / "Plan_Patterns.db"), ""))
    monkeypatch.setattr(dialogs.DimensionsDialog, "exec", lambda self: dialogs.QDialog.DialogCode.Accepted)
    window.import_db()
    project = window.session.project
    assert len(project.patterns) == 2 and all(p.origin == "db-import" for p in project.patterns)
    assert not window.act_export.isEnabled()          # imported patterns start unverified


def test_help_opens_on_f1_with_context(window, qtbot):
    load(window, qtbot, (grid(1, 1), 1))
    window.act_help.trigger()
    assert window.tabs.currentWidget() is window.help
    assert "Editor controls" in window.help.browser.toPlainText()



def test_lowering_kl_and_kb_works_in_either_order(window, qtbot):
    """KL first used to be refused (KL < old KB) and the value was lost."""
    from PyQt6.QtTest import QTest

    load(window, qtbot, (grid(2, 1), 1))
    panel = window.properties
    steps_before = window.session.undo._index
    for key, text in (("kl", "320"), ("kb", "240")):
        spin = panel.fields[key].spin
        spin.setFocus()
        spin.selectAll()
        QTest.keyClicks(spin, text)
        QTest.keyClick(spin, Qt.Key.Key_Return)
    dims = window.session.current_pattern().dims
    assert (dims.kl, dims.kb) == (320, 240)
    assert window.session.undo._index == steps_before + 1      # applied once, as a pair
    assert panel.pending.isHidden()
    assert panel.fields["kl"].value() == 320


def test_dialogs_take_no_empty_room(window, qtbot):
    d = dialogs.OptionsDialog(window.settings, window)
    d.show()
    qtbot.waitExposed(d)
    assert d.error.isHidden()
    # The fixed size is applied one event cycle after show().
    qtbot.waitUntil(lambda: d.height() <= d.layout().sizeHint().height() + 2, timeout=2000)
    d.reject()
