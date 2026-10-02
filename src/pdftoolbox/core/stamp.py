"""Draw text or images on top of (or under) existing PDF pages.

The overlay pages are drawn with Qt (QPdfWriter), which handles every script
including Arabic and right-to-left text, and embeds subsetted fonts. They are
then placed on each target page as Form XObjects with pikepdf, accounting for
the page's crop box and rotation so things appear where the reader expects.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, Iterable

import pikepdf
from pikepdf import Name

from .geometry import VisibleBox, page_visible_box

_qt_app = None


def prepare_headless_qt() -> None:
    """Pick a Qt platform for processes that draw but never show a window.

    macOS and Linux use the "offscreen" plugin, which still sees the system
    fonts. On Windows that plugin finds no fonts at all (text would silently
    vanish from stamped pages), so the normal "windows" plugin is kept; it
    opens no window unless asked to. If offscreen is forced anyway, point it
    at the Windows fonts folder.
    """
    if sys.platform.startswith("win"):
        if os.environ.get("QT_QPA_PLATFORM", "").startswith("offscreen"):
            fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
            os.environ.setdefault("QT_QPA_FONTDIR", str(fonts))
    else:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def ensure_qt():
    """Create a QGuiApplication if none exists (needed for fonts in workers)."""
    global _qt_app
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance()
    if app is None:
        prepare_headless_qt()
        _qt_app = QGuiApplication(["pdftoolbox-worker"])
        app = _qt_app
    return app


DrawFn = Callable[["QPainter", int, float, float], None]  # noqa: F821


def render_overlay(path: Path, sizes: list[tuple[float, float]], draw: DrawFn) -> Path:
    """Write a PDF with one page per size, calling ``draw(painter, i, w, h)``.

    Coordinates are PDF points with the origin at the top-left corner.
    """
    ensure_qt()
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter

    writer = QPdfWriter(str(path))
    writer.setResolution(72)
    writer.setCreator("PDF Toolbox")

    def set_size(w: float, h: float) -> None:
        size = QPageSize(QSizeF(w, h), QPageSize.Unit.Point, "", QPageSize.SizeMatchPolicy.ExactMatch)
        layout = QPageLayout(size, QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)
        writer.setPageLayout(layout)

    if not sizes:
        sizes = [(612.0, 792.0)]
    set_size(*sizes[0])
    painter = QPainter()
    if not painter.begin(writer):
        raise RuntimeError("Could not start drawing the overlay.")
    try:
        for i, (w, h) in enumerate(sizes):
            if i:
                set_size(w, h)
                writer.newPage()
            painter.save()
            draw(painter, i, w, h)
            painter.restore()
    finally:
        painter.end()
    return path


def _form_from(target: pikepdf.Pdf, overlay_page: pikepdf.Page) -> pikepdf.Object:
    form = overlay_page.as_form_xobject()
    return target.copy_foreign(form)


def place_form(page: pikepdf.Page, form: pikepdf.Object, *, under: bool = False,
               box: VisibleBox | None = None) -> None:
    """Draw ``form`` covering the page's visible area."""
    box = box or page_visible_box(page)
    bbox = [float(v) for v in form.BBox]
    fw, fh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    a, b, c, d, e, f = box.matrix(fw, fh)
    # Account for a BBox that does not start at the origin.
    e += -(a * bbox[0] + c * bbox[1])
    f += -(b * bbox[0] + d * bbox[1])
    name = page.add_resource(form, Name.XObject, prefix="Stamp")
    draw = f"q {a:.6f} {b:.6f} {c:.6f} {d:.6f} {e:.4f} {f:.4f} cm {name} Do Q\n".encode()
    if under:
        page.contents_add(draw, prepend=True)
    else:
        # Isolate the existing content so its graphics state cannot leak.
        page.contents_add(b"q\n", prepend=True)
        page.contents_add(b"Q\n" + draw, prepend=False)


def apply_overlay(target: pikepdf.Pdf, overlay: pikepdf.Pdf,
                  mapping: Iterable[tuple[int, int]], *, under: bool = False,
                  progress: Callable[[float], None] | None = None) -> None:
    """Place overlay page ``j`` on target page ``i`` for every ``(i, j)``."""
    mapping = list(mapping)
    cache: dict[int, pikepdf.Object] = {}
    for n, (i, j) in enumerate(mapping):
        if j not in cache:
            cache[j] = _form_from(target, overlay.pages[j])
        place_form(target.pages[i], cache[j], under=under)
        if progress and n % 20 == 0:
            progress(n / max(1, len(mapping)))


def visible_sizes(pdf: pikepdf.Pdf, indexes: Iterable[int]) -> list[tuple[float, float]]:
    out = []
    for i in indexes:
        box = page_visible_box(pdf.pages[i])
        out.append((box.width, box.height))
    return out
