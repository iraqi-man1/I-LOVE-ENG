import os
import sys
from pathlib import Path

import pytest

import tempfile

os.environ["PDFTOOLBOX_SETTINGS_DIR"] = tempfile.mkdtemp(prefix="pdftoolbox-test-settings-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdftoolbox.core.stamp import prepare_headless_qt  # noqa: E402
from pdftoolbox.ui import settings as _settings  # noqa: E402

prepare_headless_qt()
_settings.put("updates/auto", False)  # tests never contact GitHub


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    # One QApplication for the whole run (the stamping code reuses it).
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def _make_pdf(path: Path, pages: int = 3, *, size=(595, 842), text="Hello page", image=False, rotate=0):
    import pikepdf
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter

    from pdftoolbox.core import stamp

    def draw(painter, i, w, h):
        font = QFont()
        font.setPointSizeF(28)
        painter.setFont(font)
        painter.setPen(QColor("#1565c0"))
        painter.drawText(QRectF(50, 60, w - 100, 80), int(Qt.AlignmentFlag.AlignLeft), f"{text} {i + 1}")
        painter.fillRect(QRectF(50, 160, 200, 40), QColor("#e53935"))
        if image:
            img = QImage(400, 300, QImage.Format.Format_RGB32)
            p = QPainter(img)
            grad = QLinearGradient(0, 0, 400, 300)
            grad.setColorAt(0, QColor("red"))
            grad.setColorAt(0.5, QColor("green"))
            grad.setColorAt(1, QColor("blue"))
            p.fillRect(img.rect(), grad)
            for k in range(0, 400, 7):
                p.setPen(QColor((k * 37) % 255, (k * 91) % 255, (k * 13) % 255))
                p.drawLine(k, 0, 400 - k, 300)
            p.end()
            painter.drawImage(QRectF(50, 250, 400, 300), img)

    stamp.render_overlay(path, [size] * pages, draw)
    if rotate:
        with pikepdf.open(path, allow_overwriting_input=True) as pdf:
            for page in pdf.pages:
                page.rotate(rotate, relative=False)
            pdf.save(path)
    return path


@pytest.fixture
def make_pdf(tmp_path):
    counter = {"n": 0}

    def factory(name=None, **kwargs):
        counter["n"] += 1
        return _make_pdf(tmp_path / (name or f"doc{counter['n']}.pdf"), **kwargs)

    return factory


@pytest.fixture
def run_tool(tmp_path):
    from pdftoolbox.core.context import JobSpec
    from pdftoolbox.core.jobs import execute
    from pdftoolbox.tools import get_tool

    def runner(tool_id, files, options=None, *, output_file=None, passwords=None, expect_error=False):
        tool = get_tool(tool_id)
        opts = tool.defaults()
        opts.update(options or {})
        out_dir = tmp_path / "out"
        spec = JobSpec(tool_id, [str(f) for f in files], opts, output_dir=str(out_dir),
                       output_file=str(output_file) if output_file else None, passwords=passwords or {})
        results = execute(spec)
        if not expect_error:
            for r in results:
                assert r.error is None, f"{tool_id}: {r.error}\n{r.message}"
        return results

    return runner
