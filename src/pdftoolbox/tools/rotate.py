from __future__ import annotations

from pathlib import Path

from ..core.geometry import page_visible_box
from ..core.pages import parse_pages
from .base import ORGANIZE, Choice, Pages, Tool


def run(source: Path, ctx) -> list[Path]:
    pdf = ctx.open_pdf(source)
    angle = int(ctx.options.get("angle", 90))
    which = ctx.options.get("which", "all")
    indexes = parse_pages(ctx.options.get("pages") or "", len(pdf.pages))
    for n, i in enumerate(indexes):
        page = pdf.pages[i]
        if which != "all":
            box = page_visible_box(page)
            w, h = box.width, box.height
            if (which == "portrait" and w > h) or (which == "landscape" and h >= w):
                continue
        page.rotate(angle, relative=True)
        if n % 100 == 0:
            ctx.progress(n / max(1, len(indexes)))
    return [ctx.save_pdf(pdf, ctx.output_path(source, " (rotated)"))]


TOOL = Tool(
    id="rotate",
    name="Rotate PDF",
    category=ORGANIZE,
    description="Turn all or some pages by 90, 180 or 270 degrees.",
    icon="rotate",
    run=run,
    chainable=True,
    keywords="turn orientation landscape portrait",
    options=[
        Choice("angle", "Rotate", 90, choices=[(90, "90° clockwise"), (180, "180°"), (270, "90° counter-clockwise")]),
        Pages("pages", "Pages", ""),
        Choice("which", "Only", "all", choices=[("all", "All selected pages"), ("portrait", "Portrait pages"),
                                                   ("landscape", "Landscape pages")]),
    ],
)
