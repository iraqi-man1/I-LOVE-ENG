from __future__ import annotations

from pathlib import Path

from ..core.pages import parse_pages
from ..core.render import open_document, render_page
from .base import CONVERT, Choice, Flag, Integer, Pages, Tool


def run(source: Path, ctx) -> list[Path]:
    fmt = ctx.options.get("format", "jpg")
    dpi = int(ctx.options.get("dpi", 150))
    quality = int(ctx.options.get("quality", 90))
    gray = bool(ctx.options.get("grayscale", False))
    doc = open_document(source, ctx.password_for(source))
    try:
        indexes = parse_pages(ctx.options.get("pages") or "", len(doc))
        single = len(indexes) == 1
        folder = ctx.output_folder(source) if single else ctx.output_subfolder(source, " (images)")
        width = max(3, len(str(len(doc))))
        outputs = []
        for n, i in enumerate(indexes):
            ctx.progress(n / len(indexes), f"Page {i + 1} of {len(doc)}")
            image, scale = render_page(doc, i, dpi, grayscale=gray)
            ext = ".png" if fmt == "png" else ".jpg"
            name = f"{source.stem}{ext}" if single else f"{source.stem} - {i + 1:0{width}d}{ext}"
            from ..core.context import unique_path

            path = unique_path(folder / name)
            real_dpi = round(scale * 72)
            if fmt == "png":
                image.save(path, "PNG", optimize=False, dpi=(real_dpi, real_dpi))
            else:
                image.save(path, "JPEG", quality=quality, optimize=True, dpi=(real_dpi, real_dpi))
            outputs.append(path)
        return outputs
    finally:
        doc.close()


TOOL = Tool(
    id="pdf_to_image",
    name="PDF to JPG/PNG",
    category=CONVERT,
    description="Save each page as a JPG or PNG image.",
    icon="image",
    run=run,
    keywords="jpeg png picture export convert",
    options=[
        Choice("format", "Format", "jpg", choices=[("jpg", "JPG (smaller files)"), ("png", "PNG (lossless)")]),
        Choice("dpi", "Resolution", 150, choices=[(72, "72 dpi (screen)"), (150, "150 dpi (good)"),
                                                   (200, "200 dpi"), (300, "300 dpi (print)"), (600, "600 dpi")]),
        Integer("quality", "JPG quality", 90, minimum=10, maximum=100, suffix=" %",
                visible_when=("format", ("jpg",))),
        Flag("grayscale", "Black and white (grayscale)", False),
        Pages("pages", "Pages", ""),
    ],
)
