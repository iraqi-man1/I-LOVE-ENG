"""Application start-up."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def _setup_logging() -> None:
    from pdftoolbox.core.paths import user_data_dir

    log = user_data_dir() / "pdftoolbox.log"
    try:
        if log.exists() and log.stat().st_size > 2_000_000:
            log.unlink()
    except OSError:
        pass
    logging.basicConfig(filename=str(log), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _excepthook(exc_type, exc, tb):
    import traceback

    logging.getLogger("pdftoolbox").error("Unhandled error", exc_info=(exc_type, exc, tb))
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is not None:
            QMessageBox.warning(None, "Something went wrong",
                                "An unexpected error occurred. The app will keep running.\n\n"
                                + "".join(traceback.format_exception_only(exc_type, exc)).strip())
    except Exception:  # noqa: BLE001
        pass


def run(argv: list[str]) -> int:
    import multiprocessing

    try:
        multiprocessing.set_start_method("spawn")
    except RuntimeError:
        pass
    if "--self-test" in argv:
        from pdftoolbox.selftest import run as self_test

        index = argv.index("--self-test")
        return self_test(argv[index + 1] if len(argv) > index + 1 else None)
    _setup_logging()
    sys.excepthook = _excepthook

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from pdftoolbox import APP_ID, APP_NAME, ORG_NAME, __version__

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{ORG_NAME}.{APP_ID}")
        except Exception:  # noqa: BLE001
            pass
    class Application(QApplication):
        """Receives files opened from Finder ("Open With") on macOS."""

        window = None
        pending: list[str] = []

        def event(self, event):  # noqa: N802
            from PySide6.QtCore import QEvent

            if event.type() == QEvent.Type.FileOpen:
                path = event.file()
                if self.window is not None:
                    self.window._open_files([path])
                else:
                    self.pending.append(path)
                return True
            return super().event(event)

    app = Application(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(__version__)

    from pdftoolbox.ui import icons, settings, theme
    from pdftoolbox.ui.main_window import MainWindow

    theme.apply(app, settings.theme())
    app.setWindowIcon(icons.app_icon())
    files = [a for a in argv[1:] if not a.startswith("-") and Path(a).exists()]
    window = MainWindow(files + app.pending)
    app.window = window
    window.show()
    if os.environ.get("PDFTOOLBOX_SMOKE_TEST"):
        # Used by CI: start, show the window, then quit.
        from PySide6.QtCore import QTimer

        QTimer.singleShot(int(os.environ.get("PDFTOOLBOX_SMOKE_TEST", "1500")), app.quit)
    return app.exec()
