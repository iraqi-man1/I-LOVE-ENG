from __future__ import annotations

from pathlib import Path

import pikepdf

from .base import COMBINE, ORGANIZE, Flag, Tool


def run(files: list[Path], ctx) -> list[Path]:
    out = ctx.combined_output_path("merged", ".pdf")
    bookmarks = ctx.options.get("bookmarks", True)
    blank = ctx.options.get("blank_for_odd", False)
    merged = pikepdf.new()
    starts: list[tuple[str, int]] = []
    sources = []
    for n, path in enumerate(files):
        ctx.progress(n / len(files), f"Adding {path.name}")
        src = ctx.open_pdf(path)
        sources.append(src)  # keep open until the merged file is saved
        starts.append((path.stem, len(merged.pages)))
        merged.pages.extend(src.pages)
        if blank and len(src.pages) % 2 == 1 and n < len(files) - 1:
            last = merged.pages[-1]
            box = [float(v) for v in last.mediabox]
            merged.add_blank_page(page_size=(box[2] - box[0], box[3] - box[1]))
    if bookmarks:
        with merged.open_outline() as outline:
            for title, index in starts:
                outline.root.append(pikepdf.OutlineItem(title, index))
    ctx.progress(0.95, "Saving")
    ctx.save_pdf(merged, out)
    for src in sources:
        src.close()
    return [out]


TOOL = Tool(
    id="merge",
    name="Merge PDF",
    category=ORGANIZE,
    description="Combine several PDF files into one, in the order you choose.",
    icon="merge",
    mode=COMBINE,
    min_files=2,
    output_name="merged",
    run=run,
    keywords="combine join append",
    options=[
        Flag("bookmarks", "Add a bookmark for each file", True),
        Flag("blank_for_odd", "Insert a blank page after files with an odd number of pages", False,
             help="Useful for double-sided printing, so every file starts on a new sheet."),
    ],
)
