"""Self-test for the packaged app: `PDF Toolbox --self-test REPORT.txt`.

Exercises the worker process, the PDF engines and OCR inside the frozen
build, which unit tests running from source cannot cover.
"""

from __future__ import annotations

import multiprocessing as mp
import tempfile
import traceback
from pathlib import Path


def _run_job(spec, timeout=300):
    from pdftoolbox.core.jobs import worker_main

    ctx = mp.get_context("spawn")
    queue, cancel = ctx.Queue(), ctx.Event()
    proc = ctx.Process(target=worker_main, args=(spec, queue, cancel), daemon=True)
    proc.start()
    try:
        while True:
            kind, payload = queue.get(timeout=timeout)
            if kind == "done":
                return payload
            if kind in ("failed", "cancelled"):
                raise RuntimeError(f"{kind}: {payload}")
    finally:
        proc.join(10)


def run(report_path: str | None) -> int:
    lines = []
    ok = True
    try:
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QColor, QFont, QImage, QPainter

        from pdftoolbox import __version__
        from pdftoolbox.core import stamp
        from pdftoolbox.core.context import JobSpec
        from pdftoolbox.core.paths import find_tesseract
        from pdftoolbox.tools.ocr import installed_languages

        lines.append(f"version {__version__}")
        tmp = Path(tempfile.mkdtemp(prefix="pdftoolbox-selftest-"))
        sample = tmp / "sample.pdf"

        def draw(p, i, w, h):
            font = QFont()
            font.setPointSizeF(24)
            p.setFont(font)
            p.drawText(QRectF(40, 40, w - 80, 60), int(Qt.AlignmentFlag.AlignLeft), f"Self test page {i + 1}")

        stamp.render_overlay(sample, [(595, 842)] * 3, draw)
        results = _run_job(JobSpec("rotate", [str(sample)], {"angle": 90, "pages": "", "which": "all"},
                                   output_dir=str(tmp)))
        assert not results[0].error, results[0].error
        lines.append("worker + pikepdf: ok")
        results = _run_job(JobSpec("pdf_to_image", [str(sample)], {"format": "png", "dpi": 72, "pages": "1",
                                                                  "quality": 90, "grayscale": False},
                                   output_dir=str(tmp)))
        assert not results[0].error and results[0].outputs, results[0].error
        lines.append("pdfium render: ok")
        results = _run_job(JobSpec("page_numbers", [str(sample)], {}, output_dir=str(tmp)))
        assert not results[0].error, results[0].error
        lines.append("stamping: ok")

        exe = find_tesseract()
        lines.append(f"tesseract: {exe}")
        langs = sorted(installed_languages())
        lines.append(f"ocr languages: {', '.join(langs) or 'none'}")
        if exe and "eng" in langs:
            img = QImage(1240, 400, QImage.Format.Format_RGB32)
            img.fill(QColor("white"))
            painter = QPainter(img)
            f = QFont()
            f.setPixelSize(60)
            painter.setFont(f)
            painter.setPen(QColor("black"))
            painter.drawText(QRectF(60, 120, 1100, 200), int(Qt.AlignmentFlag.AlignLeft), "Searchable 2468")
            painter.end()
            png = tmp / "scan.png"
            img.save(str(png))
            results = _run_job(JobSpec("scan_save", [str(png)], {"quality": "balanced", "ocr": True,
                                                                "languages": ["eng"]},
                                       output_file=str(tmp / "scan.pdf")))
            assert not results[0].error, results[0].error
            import pypdfium2 as pdfium

            doc = pdfium.PdfDocument(results[0].outputs[0])
            text = doc[0].get_textpage().get_text_range()
            assert "2468" in text, f"OCR text was {text!r}"
            lines.append("ocr: ok")
        else:
            lines.append("ocr: SKIPPED (not bundled)")
            ok = False
    except Exception:  # noqa: BLE001
        ok = False
        lines.append("FAILED\n" + traceback.format_exc())
    lines.append("RESULT: " + ("PASS" if ok else "FAIL"))
    text = "\n".join(lines)
    if report_path:
        Path(report_path).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0 if ok else 1
