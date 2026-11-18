"""Background tasks on QThreadPool with progress, cancellation and stale-result protection.

A task is a plain callable `fn(cancel, progress)`; it must not touch Qt widgets or
graphics items. Each channel ("thumbnails", "recognition", ...) has a generation
number: starting, cancelling or invalidating a channel bumps it, and any signal that
arrives with an older generation is dropped. So a late result can never overwrite a
newer page, region or project.
"""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def __call__(self) -> bool:
        return self._event.is_set()


class _Signals(QObject):
    progress = pyqtSignal(int, object)
    finished = pyqtSignal(int, object)
    failed = pyqtSignal(int, str, str)
    cancelled = pyqtSignal(int)


class _Task(QRunnable):
    def __init__(self, fn, generation: int, token: CancelToken, signals: _Signals) -> None:
        super().__init__()
        self.fn, self.generation, self.token, self.signals = fn, generation, token, signals

    def run(self) -> None:
        from layerforge.domain.cancel import Cancelled

        gen = self.generation
        try:
            result = self.fn(self.token, lambda payload: self.signals.progress.emit(gen, payload))
        except Cancelled:
            self.signals.cancelled.emit(gen)
        except Exception as exc:  # noqa: BLE001 - reported to the GUI, never raised there
            self.signals.failed.emit(gen, str(exc) or exc.__class__.__name__, traceback.format_exc())
        else:
            if self.token():
                self.signals.cancelled.emit(gen)
            else:
                self.signals.finished.emit(gen, result)


@dataclass
class _Running:
    generation: int
    token: CancelToken
    signals: _Signals


class TaskRunner(QObject):
    def __init__(self, parent: QObject | None = None, threads: int = 2) -> None:
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(threads)
        self._generation: dict[str, int] = {}
        self._running: dict[str, _Running] = {}

    def generation(self, channel: str) -> int:
        return self._generation.get(channel, 0)

    def busy(self, channel: str) -> bool:
        return channel in self._running

    def start(self, channel: str, fn, on_done: Callable, on_error: Callable | None = None,
              on_progress: Callable | None = None, on_cancel: Callable | None = None) -> int:
        """Run `fn` in the background; a running task of the same channel is cancelled."""
        self.cancel(channel)
        gen = self._generation.get(channel, 0) + 1
        self._generation[channel] = gen
        token = CancelToken()
        signals = _Signals()        # created here, so it lives in the GUI thread

        def current(g: int) -> bool:
            return g == self._generation.get(channel)

        def done(g, result):
            if current(g):
                self._running.pop(channel, None)
                on_done(result)

        def failed(g, message, details):
            if current(g):
                self._running.pop(channel, None)
                if on_error is not None:
                    on_error(message, details)

        def cancelled(g):
            if current(g):
                self._running.pop(channel, None)
                if on_cancel is not None:
                    on_cancel()

        signals.finished.connect(done)
        signals.failed.connect(failed)
        signals.cancelled.connect(cancelled)
        if on_progress is not None:
            signals.progress.connect(lambda g, payload: current(g) and on_progress(payload))
        self._running[channel] = _Running(gen, token, signals)
        self.pool.start(_Task(fn, gen, token, signals))
        return gen

    def cancel(self, channel: str) -> None:
        """Ask the task to stop and ignore whatever it still delivers."""
        running = self._running.pop(channel, None)
        if running is None:
            return
        running.token.cancel()
        self._generation[channel] = self._generation.get(channel, 0) + 1

    def invalidate(self, channel: str) -> None:
        """Results of the current task are no longer wanted (page, region or project changed)."""
        self.cancel(channel)

    def shutdown(self) -> None:
        for channel in list(self._running):
            self.cancel(channel)
        self.pool.waitForDone(3000)
