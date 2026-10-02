from __future__ import annotations

from pathlib import Path

import pikepdf

from ..core.context import unique_path
from ..core.pages import parse_pages
from .base import CONVERT, Choice, Integer, Pages, Tool


def run(source: Path, ctx) -> list[Path]:
    pdf = ctx.open_pdf(source)
    indexes = parse_pages(ctx.options.get("pages") or "", len(pdf.pages))
    min_size = int(ctx.options.get("min_size", 32))
    fmt = ctx.options.get("format", "original")
    folder = None
    seen: set[tuple[int, int]] = set()
    outputs: list[Path] = []
    skipped = 0

    def walk(resources, page_no: int):
        nonlocal folder, skipped
        xobjects = resources.get("/XObject") if resources is not None else None
        if xobjects is None:
            return
        for key in list(xobjects.keys()):
            obj = xobjects[key]
            if not isinstance(obj, pikepdf.Stream):
                continue
            subtype = obj.get("/Subtype")
            if subtype == "/Form":
                if obj.objgen not in seen:
                    seen.add(obj.objgen)
                    walk(obj.get("/Resources"), page_no)
                continue
            if subtype != "/Image" or obj.objgen in seen:
                continue
            seen.add(obj.objgen)
            if obj.get("/ImageMask", False):
                continue
            if int(obj.get("/Width", 0)) < min_size or int(obj.get("/Height", 0)) < min_size:
                continue
            if folder is None:
                folder = ctx.output_subfolder(source, " (images)")
            base = folder / f"page {page_no + 1} - image {len(outputs) + 1}"
            try:
                image = pikepdf.PdfImage(obj)
                if fmt == "original":
                    written = image.extract_to(fileprefix=str(base))
                    outputs.append(Path(written))
                else:
                    pil = image.as_pil_image()
                    if pil.mode not in ("RGB", "L", "RGBA", "LA"):
                        pil = pil.convert("RGB")
                    if fmt == "jpg":
                        path = unique_path(base.with_suffix(".jpg"))
                        pil.convert("RGB" if pil.mode != "L" else "L").save(path, "JPEG", quality=92)
                    else:
                        path = unique_path(base.with_suffix(".png"))
                        pil.save(path, "PNG")
                    outputs.append(path)
            except Exception:  # noqa: BLE001 - unusual encodings are skipped
                skipped += 1

    for n, i in enumerate(indexes):
        ctx.progress(n / len(indexes), f"Page {i + 1}")
        page = pdf.pages[i]
        walk(page.obj.get("/Resources"), i)
    if not outputs:
        ctx.note("No images were found in the selected pages.")
    if skipped:
        ctx.note(f"{skipped} image{'s' if skipped != 1 else ''} used an unusual format and were skipped.")
    return outputs


TOOL = Tool(
    id="extract_images",
    name="Extract images",
    category=CONVERT,
    description="Save every picture embedded in a PDF as a separate file.",
    icon="images",
    run=run,
    keywords="pictures photos export save",
    options=[
        Choice("format", "Save as", "original", choices=[("original", "Original format (no quality loss)"),
                                                         ("png", "PNG"), ("jpg", "JPG")]),
        Integer("min_size", "Skip images smaller than", 32, minimum=0, maximum=5000, suffix=" px"),
        Pages("pages", "Pages", ""),
    ],
)
