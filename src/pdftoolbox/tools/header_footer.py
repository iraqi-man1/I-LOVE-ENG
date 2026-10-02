from __future__ import annotations

from pathlib import Path

import pikepdf

from ..core import stamp
from ..core.errors import ToolError
from ..core.pages import parse_pages
from ._stamping import MM, draw_text, expand_tokens, make_color, make_font, margin_option, text_options
from .base import EDIT, Flag, Integer, Pages, Text, Tool

SLOTS = ("header_left", "header_center", "header_right", "footer_left", "footer_center", "footer_right")
TOKENS_HELP = "You can use {page}, {total}, {filename}, {title}, {date} and {year}."


def run(source: Path, ctx) -> list[Path]:
    o = ctx.options
    texts = {slot: (o.get(slot) or "") for slot in SLOTS}
    if not any(t.strip() for t in texts.values()):
        raise ToolError("Type text for at least one header or footer position.")
    pdf = ctx.open_pdf(source)
    indexes = parse_pages(o.get("pages") or "", len(pdf.pages))
    skip = int(o.get("skip", 0))
    indexes = indexes[skip:]
    total = len(pdf.pages)
    title = ""
    try:
        title = str(pdf.docinfo.get("/Title", "") or "")
    except Exception:  # noqa: BLE001
        pass
    margin = float(o.get("margin", 10)) * MM
    side = float(o.get("side_margin", 15)) * MM
    lines = bool(o.get("lines", False))
    sizes = stamp.visible_sizes(pdf, indexes)
    state = {}

    def draw(painter, k, w, h):
        from PySide6.QtCore import QLineF
        from PySide6.QtGui import QFontMetricsF, QPen

        if "font" not in state:
            state["font"] = make_font(o)
        painter.setFont(state["font"])
        color = make_color(o.get("color", "#333333"))
        painter.setPen(color)
        page_no = indexes[k] + 1
        for slot, template in texts.items():
            if not template.strip():
                continue
            text = expand_tokens(template, page=page_no, total=total, source=source, title=title)
            region, _, horizontal = slot.partition("_")
            x = {"left": side, "center": w / 2, "right": w - side}[horizontal]
            if region == "header":
                draw_text(painter, text, x, margin, horizontal, "top")
            else:
                draw_text(painter, text, x, h - margin, horizontal, "bottom")
        if lines:
            m = QFontMetricsF(painter.font())
            pen = QPen(color)
            pen.setWidthF(0.5)
            painter.setPen(pen)
            gap = m.lineSpacing() * 1.4
            if any(texts[s].strip() for s in SLOTS[:3]):
                painter.drawLine(QLineF(side, margin + gap, w - side, margin + gap))
            if any(texts[s].strip() for s in SLOTS[3:]):
                painter.drawLine(QLineF(side, h - margin - gap, w - side, h - margin - gap))

    if indexes:
        overlay_path = ctx.temp_dir / "header_footer.pdf"
        ctx.progress(0.05, "Drawing headers and footers")
        stamp.render_overlay(overlay_path, sizes, draw)
        overlay = pikepdf.open(overlay_path)
        stamp.apply_overlay(pdf, overlay, [(i, k) for k, i in enumerate(indexes)],
                            progress=lambda f: ctx.progress(0.3 + 0.6 * f))
    ctx.progress(0.9, "Saving")
    return [ctx.save_pdf(pdf, ctx.output_path(source, " (header and footer)"))]


TOOL = Tool(
    id="header_footer",
    name="Header and footer",
    category=EDIT,
    description="Add text at the top or bottom of every page, such as a title, date or page count.",
    icon="header",
    run=run,
    chainable=True,
    keywords="heading running title date",
    options=[
        Text("header_left", "Header left", "", help=TOKENS_HELP),
        Text("header_center", "Header centre", ""),
        Text("header_right", "Header right", ""),
        Text("footer_left", "Footer left", "{filename}"),
        Text("footer_center", "Footer centre", ""),
        Text("footer_right", "Footer right", "Page {page} of {total}"),
        *text_options(9, "#333333"),
        margin_option(10),
        Integer("side_margin", "Side margin", 15, minimum=0, maximum=200, suffix=" mm"),
        Flag("lines", "Draw a thin line under the header and above the footer", False),
        Integer("skip", "Leave out at the start", 0, minimum=0, maximum=100000, suffix=" pages"),
        Pages("pages", "Pages", ""),
    ],
)
