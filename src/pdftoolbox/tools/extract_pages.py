from __future__ import annotations

from pathlib import Path

import pikepdf

from ..core.context import unique_path
from ..core.pages import parse_pages
from .base import ORGANIZE, Choice, Pages, Tool


def run(source: Path, ctx) -> list[Path]:
    src = ctx.open_pdf(source)
    indexes = parse_pages(ctx.options.get("pages") or "", len(src.pages))
    if ctx.options.get("separate") == "separate":
        folder = ctx.output_subfolder(source, " (pages)")
        outputs = []
        for n, i in enumerate(indexes):
            ctx.progress(n / len(indexes))
            out = pikepdf.new()
            out.pages.append(src.pages[i])
            outputs.append(ctx.save_pdf(out, unique_path(folder / f"{source.stem} - page {i + 1}.pdf")))
        return outputs
    out = pikepdf.new()
    for n, i in enumerate(indexes):
        out.pages.append(src.pages[i])
        if n % 50 == 0:
            ctx.progress(n / len(indexes))
    return [ctx.save_pdf(out, ctx.output_path(source, " (extracted)"))]


TOOL = Tool(
    id="extract_pages",
    name="Extract pages",
    category=ORGANIZE,
    description="Copy the pages you pick into a new PDF.",
    icon="extract",
    run=run,
    chainable=True,
    keywords="select pick copy",
    options=[
        Pages("pages", "Pages to extract", "", placeholder="e.g. 1-3, 5, 8-",
              help="Pages are written in the order you type them."),
        Choice("separate", "Output", "single", choices=[
            ("single", "One PDF with all selected pages"),
            ("separate", "A separate PDF for each page"),
        ]),
    ],
)
