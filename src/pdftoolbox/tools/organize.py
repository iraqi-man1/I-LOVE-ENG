from __future__ import annotations

from pathlib import Path

import pikepdf

from ..core.errors import ToolError
from ..core.pages import parse_pages
from .base import ORGANIZE, Choice, PageOrganizer, Text, Tool


def run(source: Path, ctx) -> list[Path]:
    src = ctx.open_pdf(source)
    total = len(src.pages)
    method = ctx.options.get("method", "visual")
    if method == "visual":
        layout = ctx.options.get("layout") or []
        if not layout:
            raise ToolError("Arrange the pages first.")
        # layout: list of {"page": original index, "rotate": extra degrees}
        entries = [(int(e["page"]), int(e.get("rotate", 0))) for e in layout]
    elif method == "reverse":
        entries = [(i, 0) for i in range(total - 1, -1, -1)]
    elif method == "interleave":
        # Scanned fronts followed by backs in reverse: 1, n, 2, n-1 ...
        half = (total + 1) // 2
        fronts, backs = list(range(half)), list(range(total - 1, half - 1, -1))
        entries = []
        for k in range(half):
            entries.append((fronts[k], 0))
            if k < len(backs):
                entries.append((backs[k], 0))
    else:
        order = parse_pages(ctx.options.get("order") or "", total)
        if ctx.options.get("append_rest", True):
            listed = set(order)
            order += [i for i in range(total) if i not in listed]
        entries = [(i, 0) for i in order]
    for page_index, _ in entries:
        if not 0 <= page_index < total:
            raise ToolError("The page layout does not match this file. Reload the file and try again.")
    out = pikepdf.new()
    for n, (page_index, rotate) in enumerate(entries):
        out.pages.append(src.pages[page_index])
        if rotate % 360:
            out.pages[-1].rotate(rotate % 360, relative=True)
        if n % 50 == 0:
            ctx.progress(n / max(1, len(entries)))
    ctx.progress(0.9, "Saving")
    return [ctx.save_pdf(out, ctx.output_path(source, " (organized)"))]


TOOL = Tool(
    id="organize",
    name="Reorder pages",
    category=ORGANIZE,
    description="Drag pages into a new order, rotate or remove them, and save the result.",
    icon="reorder",
    run=run,
    max_files=None,
    keywords="organize arrange sort move rearrange reverse",
    options=[
        Choice("method", "How", "visual", choices=[
            ("visual", "Arrange visually"),
            ("order", "Type a new order"),
            ("reverse", "Reverse all pages"),
            ("interleave", "Merge fronts and backs (1, n, 2, n-1, ...)"),
        ], help="Visual arranging works on one file at a time."),
        PageOrganizer("layout", "Pages", None, visible_when=("method", ("visual",))),
        Text("order", "New page order", "", placeholder="e.g. 3, 1, 2, 5-10",
             visible_when=("method", ("order",))),
    ],
)
