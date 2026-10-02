from __future__ import annotations

import os
from pathlib import Path

from ._optimize import clean_document, dedupe_images
from .base import OPTIMIZE, Flag, Tool


def run(source: Path, ctx) -> list[Path]:
    o = ctx.options
    pdf = ctx.open_pdf(source)
    ctx.progress(0.1, "Merging duplicate images")
    duplicates = dedupe_images(pdf)
    ctx.progress(0.4, "Removing unused data")
    clean_document(pdf, metadata=bool(o.get("strip_metadata")), javascript=bool(o.get("strip_js")))
    out = ctx.output_path(source, " (optimized)")
    ctx.progress(0.6, "Saving")
    ctx.save_pdf(pdf, out, recompress_flate=True, linearize=bool(o.get("linearize", True)))
    before, after = os.path.getsize(source), os.path.getsize(out)
    change = f"{100 - after * 100 / before:.0f}% smaller" if after < before else "about the same size"
    extra = f", merged {duplicates} duplicate image{'s' if duplicates != 1 else ''}" if duplicates else ""
    ctx.note(f"{after / 1048576:.2f} MB, {change}{extra}. Quality is unchanged.")
    return [out]


TOOL = Tool(
    id="optimize",
    name="Optimize PDF",
    category=OPTIMIZE,
    description="Clean up and restructure a PDF without any loss of quality, and enable fast web view.",
    icon="optimize",
    run=run,
    chainable=True,
    keywords="lossless clean linearize fast web view",
    options=[
        Flag("linearize", "Fast web view (opens page by page over a network)", True),
        Flag("strip_metadata", "Remove document metadata", False),
        Flag("strip_js", "Remove JavaScript and automatic actions", False),
    ],
)
