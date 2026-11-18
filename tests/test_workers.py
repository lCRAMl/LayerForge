"""Background tasks: GUI stays responsive, stale and cancelled results are not applied."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer  # noqa: E402

from layerpattern.presentation.workers import TaskRunner  # noqa: E402


def slow(seconds, value):
    def fn(cancel, progress):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if cancel():
                from layerpattern.infrastructure.recognition.detect import Cancelled
                raise Cancelled()
            time.sleep(0.01)
        progress("half")
        return value
    return fn


def test_long_task_does_not_block_the_event_loop(qtbot):
    runner = TaskRunner()
    ticks, results = [], []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(20)
    runner.start("job", slow(0.4, 42), results.append)
    qtbot.waitUntil(lambda: results == [42], timeout=3000)
    timer.stop()
    assert len(ticks) >= 8          # the GUI thread kept running while the task worked


def test_newer_task_wins_and_stale_result_is_dropped(qtbot):
    runner = TaskRunner()
    results = []
    runner.start("page", slow(0.3, "old page"), results.append)
    runner.start("page", slow(0.05, "new page"), results.append)
    qtbot.wait(600)
    assert results == ["new page"]


def test_cancel_reports_and_applies_nothing(qtbot):
    runner = TaskRunner()
    results, cancelled = [], []
    runner.start("rec", slow(2.0, "x"), results.append, on_cancel=lambda: cancelled.append(1))
    runner.cancel("rec")
    qtbot.wait(300)
    assert results == [] and not runner.busy("rec")


def test_invalidate_drops_a_finished_result_that_arrives_late(qtbot):
    runner = TaskRunner()
    results = []
    runner.start("rec", slow(0.2, "late"), results.append)
    runner.invalidate("rec")              # e.g. the project was replaced meanwhile
    qtbot.wait(500)
    assert results == []


def test_errors_arrive_with_details(qtbot):
    runner = TaskRunner()
    errors = []

    def broken(_cancel, _progress):
        raise ValueError("bad page")

    runner.start("rec", broken, lambda _r: None, on_error=lambda m, d: errors.append((m, d)))
    qtbot.waitUntil(lambda: bool(errors), timeout=2000)
    assert errors[0][0] == "bad page" and "ValueError" in errors[0][1]


def test_progress_is_delivered(qtbot):
    runner = TaskRunner()
    progress, results = [], []
    runner.start("rec", slow(0.05, 1), results.append, on_progress=progress.append)
    qtbot.waitUntil(lambda: bool(results), timeout=2000)
    assert progress == ["half"]
