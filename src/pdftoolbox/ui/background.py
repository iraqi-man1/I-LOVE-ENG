"""Background work that never holds up, or crashes, quitting the app."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal


class Worker(QObject):
    """Runs ``run()`` on a daemon thread; its signals arrive on the GUI thread.

    A QThread that is still running when the app exits aborts the whole
    process, and a slow network request or scanner is enough for that. A
    daemon thread is simply abandoned instead. Give the worker a parent
    widget; it deletes itself once it has finished.
    """

    finished = Signal()

    def start(self) -> None:
        self.finished.connect(self.deleteLater)
        threading.Thread(target=self._main, name=type(self).__name__, daemon=True).start()

    def run(self) -> None:
        raise NotImplementedError

    def _main(self) -> None:
        try:
            try:
                self.run()
            finally:
                self.finished.emit()
        except RuntimeError:
            pass  # the window that started the work was closed meanwhile
