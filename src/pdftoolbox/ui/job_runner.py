"""Runs jobs in a separate process and reports back to the interface.

A separate process keeps the window responsive however large the files are,
and if a damaged document crashes the PDF engine only that job fails.
"""

from __future__ import annotations

import multiprocessing as mp
import queue as queue_module

from PySide6.QtCore import QObject, QTimer, Signal

from pdftoolbox.core.context import JobSpec
from pdftoolbox.core.jobs import worker_main


class JobRunner(QObject):
    progress = Signal(float, str)
    file_done = Signal(object)
    finished = Signal(list)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx = mp.get_context("spawn")
        self._process = None
        self._queue = None
        self._cancel = None
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._poll)
        self._cancel_requested = False
        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.timeout.connect(self._kill)

    @property
    def running(self) -> bool:
        return self._process is not None

    def start(self, spec: JobSpec) -> None:
        if self.running:
            raise RuntimeError("A job is already running")
        self._queue = self._ctx.Queue()
        self._cancel = self._ctx.Event()
        self._cancel_requested = False
        self._process = self._ctx.Process(target=worker_main, args=(spec, self._queue, self._cancel), daemon=True)
        self._process.start()
        self._timer.start()

    def cancel(self) -> None:
        if not self.running:
            return
        self._cancel_requested = True
        self._cancel.set()
        # Give the job a moment to stop cleanly, then end the process.
        self._kill_timer.start(4000)

    def _kill(self) -> None:
        if self._process is not None and self._process.is_alive():
            self._process.terminate()

    def _finish(self) -> None:
        self._timer.stop()
        self._kill_timer.stop()
        if self._process is not None:
            self._process.join(timeout=2)
            if self._process.is_alive():
                self._process.kill()
        self._process = None
        self._queue = None

    def _poll(self) -> None:
        if self._queue is None:
            return
        for _ in range(200):
            try:
                kind, payload = self._queue.get_nowait()
            except queue_module.Empty:
                break
            except (EOFError, OSError):
                break
            if kind == "progress":
                fraction, message = payload
                self.progress.emit(float(fraction), message or "")
            elif kind == "file-done":
                self.file_done.emit(payload)
            elif kind == "done":
                self._finish()
                self.finished.emit(payload)
                return
            elif kind == "cancelled":
                self._finish()
                self.cancelled.emit()
                return
            elif kind == "failed":
                self._finish()
                self.failed.emit(payload)
                return
        if self._process is not None and not self._process.is_alive():
            # Drain anything left, then report an unexpected exit.
            try:
                while True:
                    kind, payload = self._queue.get(timeout=0.2)
                    if kind == "done":
                        self._finish()
                        self.finished.emit(payload)
                        return
            except Exception:  # noqa: BLE001
                pass
            code = self._process.exitcode
            self._finish()
            if self._cancel_requested:
                self.cancelled.emit()
            else:
                self.failed.emit(
                    "The document processor stopped unexpectedly"
                    + (f" (code {code})" if code else "")
                    + ". The file may be damaged; try Repair PDF first.")
