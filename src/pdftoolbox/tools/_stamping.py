"""Shared helpers for tools that draw text on pages."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from .base import Choice, Color, Font, Integer, Number

MM = 72 / 25.4

POSITIONS = [
    ("top-left", "Top left"), ("top-center", "Top centre"), ("top-right", "Top right"),
    ("middle-left", "Middle left"), ("center", "Centre"), ("middle-right", "Middle right"),
    ("bottom-left", "Bottom left"), ("bottom-center", "Bottom centre"), ("bottom-right", "Bottom right"),
]


def text_options(size: int = 11, color: str = "#000000") -> list:
    return [
        Font("font", "Font", ""),
        Integer("size", "Font size", size, minimum=4, maximum=400, suffix=" pt"),
        Color("color", "Colour", color),
        Choice("weight", "Style", "normal", choices=[("normal", "Regular"), ("bold", "Bold"), ("italic", "Italic"),
                                                    ("bolditalic", "Bold italic")]),
    ]


def margin_option(default: float = 12.0):
    return Number("margin", "Distance from edge", default, maximum=200, suffix=" mm")


def make_font(options: dict, size: float | None = None):
    from PySide6.QtGui import QFont

    font = QFont()
    family = options.get("font") or ""
    if family:
        font.setFamily(family)
    else:
        font.setFamilies(["Helvetica", "Arial", "Segoe UI", "DejaVu Sans", "Noto Sans"])
    font.setPointSizeF(float(size if size is not None else options.get("size", 11)))
    weight = options.get("weight", "normal")
    font.setBold("bold" in weight)
    font.setItalic("italic" in weight)
    return font


def make_color(value: str, opacity: float = 1.0):
    from PySide6.QtGui import QColor

    color = QColor(value or "#000000")
    if not color.isValid():
        color = QColor("#000000")
    color.setAlphaF(max(0.0, min(1.0, opacity)))
    return color


def anchor_point(position: str, w: float, h: float, margin: float) -> tuple[float, float, str, str]:
    """Return (x, y, horizontal, vertical) alignment for a 9-grid position."""
    vertical, _, horizontal = position.partition("-") if "-" in position else ("middle", "", "center")
    if position == "center":
        vertical, horizontal = "middle", "center"
    x = {"left": margin, "center": w / 2, "right": w - margin}[horizontal]
    y = {"top": margin, "middle": h / 2, "bottom": h - margin}[vertical]
    return x, y, horizontal, vertical


def draw_text(painter, text: str, x: float, y: float, horizontal: str, vertical: str, rotation: float = 0.0) -> None:
    """Draw (possibly multi-line) text aligned to the point (x, y)."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QFontMetricsF

    metrics = QFontMetricsF(painter.font())
    lines = text.split("\n")
    width = max((metrics.horizontalAdvance(line) for line in lines), default=0.0)
    height = metrics.lineSpacing() * len(lines)
    align = {"left": Qt.AlignmentFlag.AlignLeft, "center": Qt.AlignmentFlag.AlignHCenter,
             "right": Qt.AlignmentFlag.AlignRight}[horizontal]
    painter.save()
    painter.translate(x, y)
    if rotation:
        painter.rotate(rotation)
    left = {"left": 0.0, "center": -width / 2, "right": -width}[horizontal]
    top = {"top": 0.0, "middle": -height / 2, "bottom": -height}[vertical]
    painter.drawText(QRectF(left - 2, top, width + 4, height + 2), int(align | Qt.AlignmentFlag.AlignTop), text)
    painter.restore()


def expand_tokens(template: str, *, page: int, total: int, source: Path, title: str = "") -> str:
    today = _dt.date.today()
    values = {
        "page": str(page), "n": str(page), "total": str(total), "pages": str(total),
        "filename": source.stem, "file": source.name, "date": today.isoformat(),
        "date_local": today.strftime("%d/%m/%Y"), "year": str(today.year), "title": title or source.stem,
    }
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out
