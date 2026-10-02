from __future__ import annotations

from pathlib import Path

import pikepdf

from ..core import stamp
from ..core.pages import parse_pages
from ._stamping import MM, anchor_point, draw_text, expand_tokens, make_color, make_font, margin_option, text_options
from .base import EDIT, Choice, Flag, Integer, Pages, Text, Tool

FORMATS = [
    ("{n}", "1, 2, 3"),
    ("Page {n}", "Page 1"),
    ("Page {n} of {total}", "Page 1 of 10"),
    ("{n} / {total}", "1 / 10"),
    ("- {n} -", "- 1 -"),
    ("custom", "Custom..."),
]


def run(source: Path, ctx) -> list[Path]:
    o = ctx.options
    pdf = ctx.open_pdf(source)
    indexes = parse_pages(o.get("pages") or "", len(pdf.pages))
    fmt = o.get("format", "{n}")
    if fmt == "custom":
        fmt = o.get("custom") or "{n}"
    start = int(o.get("start", 1))
    skip = int(o.get("skip", 0))
    numbered = indexes[skip:]
    total = len(numbered) + start - 1 if o.get("total_mode", "numbered") == "numbered" else len(pdf.pages)
    position = o.get("position", "bottom-center")
    mirror = bool(o.get("mirror", False))
    margin = float(o.get("margin", 12)) * MM
    sizes = stamp.visible_sizes(pdf, numbered)
    font = None

    def draw(painter, k, w, h):
        nonlocal font
        if font is None:
            font = make_font(o)
        painter.setFont(font)
        painter.setPen(make_color(o.get("color", "#000000")))
        pos = position
        if mirror and (numbered[k] % 2 == 1):  # even page numbers in a book
            pos = pos.replace("left", "\0").replace("right", "left").replace("\0", "right")
        x, y, hz, vt = anchor_point(pos, w, h, margin)
        label = expand_tokens(fmt, page=start + k, total=total, source=source)
        draw_text(painter, label, x, y, hz, vt)

    if numbered:
        overlay_path = ctx.temp_dir / "numbers.pdf"
        ctx.progress(0.05, "Drawing page numbers")
        stamp.render_overlay(overlay_path, sizes, draw)
        overlay = pikepdf.open(overlay_path)
        stamp.apply_overlay(pdf, overlay, [(i, k) for k, i in enumerate(numbered)],
                            progress=lambda f: ctx.progress(0.3 + 0.6 * f))
    ctx.progress(0.9, "Saving")
    return [ctx.save_pdf(pdf, ctx.output_path(source, " (numbered)"))]


TOOL = Tool(
    id="page_numbers",
    name="Page numbers",
    category=EDIT,
    description="Add page numbers in the position and style you like.",
    icon="numbers",
    run=run,
    chainable=True,
    keywords="number paginate pagination bates",
    options=[
        Choice("position", "Position", "bottom-center", choices=[
            ("top-left", "Top left"), ("top-center", "Top centre"), ("top-right", "Top right"),
            ("bottom-left", "Bottom left"), ("bottom-center", "Bottom centre"), ("bottom-right", "Bottom right")]),
        Choice("format", "Format", "{n}", choices=FORMATS),
        Text("custom", "Custom format", "Page {n} of {total}",
             help="Use {n} for the page number, {total} for the page count and {filename} for the file name.",
             visible_when=("format", ("custom",))),
        Integer("start", "First number", 1, minimum=0, maximum=1000000),
        Integer("skip", "Leave unnumbered at the start", 0, minimum=0, maximum=100000, suffix=" pages",
                help="For example 1 to skip a cover page."),
        Choice("total_mode", "Total counts", "numbered", choices=[("numbered", "Numbered pages"),
                                                                   ("all", "All pages in the file")],
               visible_when=("format", ("Page {n} of {total}", "{n} / {total}", "custom"))),
        Flag("mirror", "Mirror left and right on even pages (for books)", False),
        *text_options(11),
        margin_option(12),
        Pages("pages", "Pages", ""),
    ],
)
