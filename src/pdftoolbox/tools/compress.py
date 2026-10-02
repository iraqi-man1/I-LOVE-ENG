from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

from ._images import encode_jpeg, filters_of, is_photo, load_image, replace_with_jpeg, walk_images
from ._optimize import clean_document
from .base import OPTIMIZE, Choice, Flag, Integer, Tool

LEVELS = {"low": (220, 85), "medium": (150, 72), "high": (100, 55), "extreme": (72, 40)}


def compress_images(pdf, ctx, dpi: int, quality: int, progress) -> tuple[int, int]:
    changed = saved = 0
    for obj, long_in in walk_images(pdf, progress):
        image = load_image(obj)
        if image is None:
            continue
        was_jpeg = "/DCTDecode" in filters_of(obj)
        if not was_jpeg and not is_photo(image):
            continue  # line art and screenshots keep their lossless encoding
        limit = max(16, int(long_in * dpi))
        if max(image.size) > limit * 1.05:
            ratio = limit / max(image.size)
            image = image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
                                 Image.Resampling.LANCZOS)
        elif was_jpeg and quality >= 80:
            continue  # re-encoding a JPEG at high quality gains little
        data = encode_jpeg(image, quality)
        old = len(obj.read_raw_bytes())
        if len(data) < old * 0.92:
            replace_with_jpeg(obj, image, data)
            changed += 1
            saved += old - len(data)
    return changed, saved


def run(source: Path, ctx) -> list[Path]:
    o = ctx.options
    level = o.get("level", "medium")
    if level == "custom":
        dpi, quality = int(o.get("dpi", 150)), int(o.get("quality", 70))
    else:
        dpi, quality = LEVELS[level]
    pdf = ctx.open_pdf(source)
    ctx.progress(0.02, "Compressing images")
    compress_images(pdf, ctx, dpi, quality, lambda f: ctx.progress(0.05 + 0.75 * f))
    ctx.progress(0.82, "Removing unused data")
    clean_document(pdf, metadata=bool(o.get("strip_metadata", False)))
    out = ctx.output_path(source, " (compressed)")
    ctx.progress(0.9, "Saving")
    ctx.save_pdf(pdf, out, recompress_flate=True)
    before, after = os.path.getsize(source), os.path.getsize(out)
    if after < before:
        ctx.note(f"Reduced from {before / 1048576:.2f} MB to {after / 1048576:.2f} MB "
                 f"({100 - after * 100 / before:.0f}% smaller).")
    else:
        ctx.note("This PDF is already well compressed; the new file is not smaller.")
    return [out]


TOOL = Tool(
    id="compress",
    name="Compress PDF",
    category=OPTIMIZE,
    description="Make a PDF smaller by shrinking its images, keeping text sharp.",
    icon="compress",
    run=run,
    chainable=True,
    keywords="reduce size shrink smaller email",
    options=[
        Choice("level", "Compression", "medium", choices=[
            ("low", "Light (best quality)"), ("medium", "Recommended"), ("high", "Strong (smaller file)"),
            ("extreme", "Maximum (smallest file)"), ("custom", "Custom")]),
        Integer("dpi", "Image resolution", 150, minimum=36, maximum=600, suffix=" dpi",
                visible_when=("level", ("custom",))),
        Integer("quality", "JPG quality", 70, minimum=10, maximum=95, suffix=" %", visible_when=("level", ("custom",))),
        Flag("strip_metadata", "Remove document metadata", False),
    ],
)
