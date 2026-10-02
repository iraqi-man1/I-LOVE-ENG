from __future__ import annotations

from pathlib import Path

import pikepdf

from ..core import stamp
from ..core.errors import ToolError
from ..core.pages import parse_pages
from ._stamping import POSITIONS, anchor_point, draw_text, make_color, make_font, text_options
from .base import EDIT, Choice, ImageFile, Integer, Pages, Text, Tool


def run(source: Path, ctx) -> list[Path]:
    o = ctx.options
    kind = o.get("kind", "text")
    text = (o.get("text") or "").strip()
    if kind == "text" and not text:
        raise ToolError("Type the watermark text.")
    image_path = o.get("image") or ""
    if kind == "image" and not (image_path and Path(image_path).exists()):
        raise ToolError("Choose an image for the watermark.")
    pdf = ctx.open_pdf(source)
    indexes = parse_pages(o.get("pages") or "", len(pdf.pages))
    sizes = stamp.visible_sizes(pdf, indexes)
    distinct = sorted(set((round(w, 2), round(h, 2)) for w, h in sizes))
    index_of = {size: k for k, size in enumerate(distinct)}
    opacity = int(o.get("opacity", 30)) / 100.0
    rotation = -float(o.get("rotation", 45))
    position = o.get("position", "center")

    stamp.ensure_qt()
    qimage = None
    if kind == "image":
        from PySide6.QtGui import QImage

        qimage = QImage(image_path)
        if qimage.isNull():
            raise ToolError("The watermark image could not be read.")

    def draw(painter, i, w, h):
        from PySide6.QtCore import QPointF, QRectF

        painter.setOpacity(opacity)
        if kind == "text":
            painter.setFont(make_font(o))
            painter.setPen(make_color(o.get("color", "#d32f2f")))
            if position == "tile":
                from PySide6.QtGui import QFontMetricsF

                m = QFontMetricsF(painter.font())
                step_x = max(m.horizontalAdvance(text) * 1.4, 80.0)
                step_y = max(m.lineSpacing() * 4.0, 60.0)
                y, row = -h * 0.2, 0
                while y < h * 1.2:
                    x = -w * 0.2 + (step_x / 2 if row % 2 else 0)
                    while x < w * 1.2:
                        draw_text(painter, text, x, y, "center", "middle", rotation)
                        x += step_x
                    y += step_y
                    row += 1
            else:
                margin = 36.0
                x, y, hz, vt = anchor_point(position, w, h, margin)
                draw_text(painter, text, x, y, hz, vt, rotation)
        else:
            scale = int(o.get("image_scale", 40)) / 100.0
            target_w = w * scale
            target_h = target_w * qimage.height() / max(1, qimage.width())
            if position == "tile":
                y = 0.0
                while y < h:
                    x = 0.0
                    while x < w:
                        painter.drawImage(QRectF(x, y, target_w, target_h), qimage)
                        x += target_w * 1.5
                    y += target_h * 1.5
                return
            x, y, hz, vt = anchor_point(position, w, h, 36.0)
            painter.translate(QPointF(x, y))
            if rotation:
                painter.rotate(rotation)
            left = {"left": 0.0, "center": -target_w / 2, "right": -target_w}[hz]
            top = {"top": 0.0, "middle": -target_h / 2, "bottom": -target_h}[vt]
            painter.drawImage(QRectF(left, top, target_w, target_h), qimage)

    overlay_path = ctx.temp_dir / "watermark.pdf"
    stamp.render_overlay(overlay_path, list(distinct), draw)
    overlay = pikepdf.open(overlay_path)
    mapping = [(i, index_of[(round(w, 2), round(h, 2))]) for i, (w, h) in zip(indexes, sizes)]
    stamp.apply_overlay(pdf, overlay, mapping, under=o.get("layer", "over") == "under",
                        progress=lambda f: ctx.progress(0.1 + 0.8 * f))
    ctx.progress(0.9, "Saving")
    return [ctx.save_pdf(pdf, ctx.output_path(source, " (watermarked)"))]


TOOL = Tool(
    id="watermark",
    name="Watermark",
    category=EDIT,
    description="Stamp text such as “CONFIDENTIAL” or a logo across your pages.",
    icon="watermark",
    run=run,
    chainable=True,
    keywords="stamp logo confidential draft",
    options=[
        Choice("kind", "Watermark", "text", choices=[("text", "Text"), ("image", "Image")]),
        Text("text", "Text", "CONFIDENTIAL", visible_when=("kind", ("text",))),
        ImageFile("image", "Image", "", visible_when=("kind", ("image",))),
        Integer("image_scale", "Image width", 40, minimum=1, maximum=100, suffix=" % of page",
                visible_when=("kind", ("image",))),
        *[opt for opt in text_options(60, "#d32f2f")],
        Integer("opacity", "Opacity", 30, minimum=1, maximum=100, suffix=" %"),
        Choice("rotation", "Angle", 45, choices=[(0, "Horizontal"), (45, "Diagonal (45°)"), (90, "Vertical"),
                                                 (-45, "Diagonal (-45°)")]),
        Choice("position", "Position", "center", choices=[*POSITIONS, ("tile", "Repeat across the page")]),
        Choice("layer", "Layer", "over", choices=[("over", "On top of the content"),
                                                  ("under", "Behind the content")]),
        Pages("pages", "Pages", ""),
    ],
)
# Text styling only applies to text watermarks.
for _opt in TOOL.options:
    if _opt.key in ("font", "size", "color", "weight"):
        _opt.visible_when = ("kind", ("text",))
