"""Render screenshots of the main screens (used for docs and visual checks).

Usage: python scripts/screenshots.py OUTPUT_DIR
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PDFTOOLBOX_FAKE_SCANNER", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))


def main(out: Path) -> None:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from pdftoolbox.ui import theme

    app = QApplication(sys.argv)
    theme.apply(app, os.environ.get("THEME", "light"))
    from conftest import _make_pdf

    from pdftoolbox.ui.main_window import MainWindow

    tmp = Path(tempfile.mkdtemp())
    a = _make_pdf(tmp / "Annual report.pdf", pages=6, image=True)
    b = _make_pdf(tmp / "Invoice March.pdf", pages=2)
    win = MainWindow()
    win.resize(1280, 820)
    win.show()

    def wait(ms):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    out.mkdir(parents=True, exist_ok=True)
    wait(500)
    win.grab().save(str(out / "home.png"))
    win.open_tool("merge", [str(a), str(b)])
    wait(800)
    win.grab().save(str(out / "merge.png"))
    win.open_tool("organize", [str(a)])
    wait(2500)
    win.grab().save(str(out / "organize.png"))
    win.open_tool("watermark", [str(a)])
    wait(500)
    win.grab().save(str(out / "watermark.png"))
    page = win.pages["watermark"]
    page.start()
    for _ in range(100):
        wait(200)
        if not page.runner.running:
            break
    wait(300)
    win.grab().save(str(out / "watermark_done.png"))
    win.open_tool("batch", [str(a), str(b)])
    page = win.pages["batch"]
    page.pipeline.add_step("rotate")
    page.pipeline.add_step("compress")
    wait(400)
    win.grab().save(str(out / "batch.png"))
    win.open_tool("__scan__")
    wait(1500)
    scan = win.pages["__scan__"]
    scan.scan()
    for _ in range(50):
        wait(200)
        if scan.worker is None:
            break
    scan.source_box.setCurrentIndex(1)
    scan.scan()
    for _ in range(50):
        wait(200)
        if scan.worker is None:
            break
    wait(500)
    win.grab().save(str(out / "scan.png"))
    win.open_tool("info", [str(a)])
    win.pages["info"].start()
    for _ in range(100):
        wait(200)
        if not win.pages["info"].runner.running:
            break
    wait(300)
    win.grab().save(str(out / "info.png"))
    win.close()


if __name__ == "__main__":
    main(Path(sys.argv[1]))
