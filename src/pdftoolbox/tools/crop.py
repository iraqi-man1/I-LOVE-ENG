from __future__ import annotations

from pathlib import Path

import pikepdf
from PIL import ImageOps

from ..core.errors import ToolError
from ..core.geometry import page_visible_box
from ..core.pages import parse_pages
from ..core.render import open_document, render_page
from .base import ORGANIZE, Choice, Number, Pages, Tool

MM = 72 / 25.4


def _set_visible(page: pikepdf.Page, u0: float, v0: float, u1: float, v1: float) -> None:
    """Set the crop box from a rectangle in visible (as displayed) coordinates."""
    box = page_visible_box(page)
    a, b, c, d, e, f = box.matrix(box.width, box.height)
    xs, ys = [], []
    for u, v in ((u0, v0), (u1, v1), (u0, v1), (u1, v0)):
        xs.append(a * u + c * v + e)
        ys.append(b * u + d * v + f)
    page.obj.CropBox = pikepdf.Array([min(xs), min(ys), max(xs), max(ys)])


def _content_bbox(doc, index: int, threshold: int = 245):
    image, scale = render_page(doc, index, 50, grayscale=True, annotations=True)
    mask = ImageOps.invert(image).point(lambda p: 255 if p > 255 - threshold else 0)
    bbox = mask.getbbox()
    if not bbox:
        return None
    left, top, right, bottom = bbox
    return left / scale, top / scale, right / scale, bottom / scale


def run(source: Path, ctx) -> list[Path]:
    pdf = ctx.open_pdf(source)
    indexes = parse_pages(ctx.options.get("pages") or "", len(pdf.pages))
    mode = ctx.options.get("mode", "margins")
    unit = MM if ctx.options.get("unit", "mm") == "mm" else 1.0
    if mode == "margins":
        top = float(ctx.options.get("top", 0)) * unit
        bottom = float(ctx.options.get("bottom", 0)) * unit
        left = float(ctx.options.get("left", 0)) * unit
        right = float(ctx.options.get("right", 0)) * unit
        for n, i in enumerate(indexes):
            page = pdf.pages[i]
            box = page_visible_box(page)
            if left + right >= box.width or top + bottom >= box.height:
                raise ToolError(f"The margins are larger than page {i + 1}.")
            _set_visible(page, left, bottom, box.width - right, box.height - top)
            if n % 100 == 0:
                ctx.progress(n / len(indexes))
    else:
        padding = float(ctx.options.get("padding", 5)) * unit
        doc = open_document(source, ctx.password_for(source))
        try:
            boxes = {}
            for n, i in enumerate(indexes):
                ctx.progress(0.9 * n / len(indexes), f"Finding content on page {i + 1}")
                boxes[i] = _content_bbox(doc, i)
        finally:
            doc.close()
        found = [b for b in boxes.values() if b]
        if not found:
            raise ToolError("The selected pages look blank, so there is nothing to trim to.")
        union = (min(b[0] for b in found), min(b[1] for b in found),
                 max(b[2] for b in found), max(b[3] for b in found))
        for i in indexes:
            bbox = union if mode == "auto_same" else boxes[i]
            if not bbox:
                continue
            page = pdf.pages[i]
            vis = page_visible_box(page)
            l, t, r, b = bbox
            u0, u1 = max(0.0, l - padding), min(vis.width, r + padding)
            v0, v1 = max(0.0, vis.height - b - padding), min(vis.height, vis.height - t + padding)
            _set_visible(page, u0, v0, u1, v1)
    return [ctx.save_pdf(pdf, ctx.output_path(source, " (cropped)"))]


TOOL = Tool(
    id="crop",
    name="Crop PDF",
    category=ORGANIZE,
    description="Trim page margins by a set amount, or cut away empty space automatically.",
    icon="crop",
    run=run,
    chainable=True,
    keywords="trim margins whitespace",
    options=[
        Choice("mode", "Crop", "margins", choices=[
            ("margins", "By margins"),
            ("auto", "Trim white space (each page)"),
            ("auto_same", "Trim white space (same box for all pages)"),
        ]),
        Choice("unit", "Units", "mm", choices=[("mm", "Millimetres"), ("pt", "Points")]),
        Number("top", "Top", 10, maximum=2000, visible_when=("mode", ("margins",))),
        Number("bottom", "Bottom", 10, maximum=2000, visible_when=("mode", ("margins",))),
        Number("left", "Left", 10, maximum=2000, visible_when=("mode", ("margins",))),
        Number("right", "Right", 10, maximum=2000, visible_when=("mode", ("margins",))),
        Number("padding", "Keep a border of", 5, maximum=500, visible_when=("mode", ("auto", "auto_same"))),
        Pages("pages", "Pages", ""),
    ],
)
