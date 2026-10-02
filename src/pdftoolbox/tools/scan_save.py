"""Save scanned pages as one PDF (used by the Scan to PDF screen)."""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from ..core.context import Context, JobSpec
from .base import COMBINE, IMAGE, Tool
from .image_to_pdf import images_to_pdf

QUALITY = {"small": 60, "balanced": 78, "high": 90, "lossless": None}


def run(files: list[Path], ctx) -> list[Path]:
    o = ctx.options
    rotations = o.get("rotations") or {}
    quality = QUALITY.get(o.get("quality", "balanced"), 78)
    out = ctx.combined_output_path("Scan", ".pdf")
    prepared = []
    for n, path in enumerate(files):
        ctx.progress(0.3 * n / max(1, len(files)), "Preparing pages")
        angle = int(rotations.get(str(path), 0)) % 360
        if angle:
            with Image.open(path) as im:
                dpi = im.info.get("dpi")
                turned = im.rotate(-angle, expand=True)
                target = ctx.temp_dir / f"r{n}.png"
                turned.save(target, dpi=dpi) if dpi else turned.save(target)
            prepared.append(target)
        else:
            prepared.append(path)
    q = quality
    if not o.get("ocr"):
        images_to_pdf(prepared, out, ctx, page_size="fit", quality=q)
        return [out]
    draft = ctx.temp_dir / "scan.pdf"
    images_to_pdf(prepared, draft, ctx, page_size="fit", quality=q)
    from . import get_tool

    ocr = get_tool("ocr")
    options = {**ocr.defaults(), "languages": o.get("languages") or ["eng"], "existing": "all"}

    def report(kind, payload):
        if kind == "progress":
            ctx.progress(0.4 + 0.6 * payload[0], payload[1])

    sub = Context(JobSpec("ocr", [str(draft)], options), report, ctx._is_cancelled)
    sub.forced_output_path = ctx.temp_dir / "scan-ocr.pdf"
    try:
        result = ocr.run(draft, sub)
        shutil.move(str(result[0]), str(out))
    finally:
        sub.cleanup()
    return [out]


TOOL = Tool(
    id="scan_save",
    name="Save scan",
    category="Scan",
    description="Save scanned pages as a PDF.",
    icon="scan",
    inputs=(IMAGE,),
    mode=COMBINE,
    run=run,
    hidden=True,
)
