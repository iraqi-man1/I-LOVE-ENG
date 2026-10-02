from __future__ import annotations

from pathlib import Path

from ..core.errors import ToolError
from ..core.pages import parse_pages
from .base import ORGANIZE, Pages, Tool


def run(source: Path, ctx) -> list[Path]:
    pdf = ctx.open_pdf(source)
    total = len(pdf.pages)
    remove = set(parse_pages(ctx.options.get("pages") or "", total, allow_empty=True))
    if not remove:
        raise ToolError("Enter the pages to delete, for example 2, 5-7.")
    if len(remove) >= total:
        raise ToolError("A PDF needs at least one page, so not every page can be deleted.")
    for i in sorted(remove, reverse=True):
        del pdf.pages[i]
    ctx.progress(0.8, "Saving")
    pdf.remove_unreferenced_resources()
    return [ctx.save_pdf(pdf, ctx.output_path(source, " (pages deleted)"))]


TOOL = Tool(
    id="delete_pages",
    name="Delete pages",
    category=ORGANIZE,
    description="Remove pages you don't need from a PDF.",
    icon="delete",
    run=run,
    chainable=True,
    keywords="remove drop",
    options=[Pages("pages", "Pages to delete", "", placeholder="e.g. 2, 5-7, last")],
)
