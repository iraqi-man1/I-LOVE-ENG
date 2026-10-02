"""Convert a PDF to shades of grey.

The default method keeps text and drawings as they are (sharp and
selectable) and only rewrites their colours; images are converted to grey.
The "rasterize" method renders every page as a grey image, which always
removes all colour but makes text unselectable.
"""

from __future__ import annotations

from pathlib import Path

import pikepdf
from pikepdf import Name, Operator

from ..core.pages import parse_pages
from ..core.render import open_document, render_page
from ._images import encode_jpeg, filters_of, load_image, replace_with_flate, replace_with_jpeg
from .base import OPTIMIZE, Choice, Tool
from .image_to_pdf import add_image_page, image_xobject


def _rgb_gray(r: float, g: float, b: float) -> float:
    return max(0.0, min(1.0, 0.299 * r + 0.587 * g + 0.114 * b))


def _cmyk_gray(c: float, m: float, y: float, k: float) -> float:
    return max(0.0, min(1.0, 1.0 - min(1.0, 0.3 * c + 0.59 * m + 0.11 * y + k)))


def _components(cs) -> int | None:
    """Number of components for device-like colour spaces, else None."""
    try:
        if isinstance(cs, pikepdf.Name):
            return {"/DeviceRGB": 3, "/DeviceCMYK": 4, "/DeviceGray": 1, "/CalRGB": 3, "/CalGray": 1}.get(str(cs))
        if isinstance(cs, pikepdf.Array) and len(cs):
            kind = str(cs[0])
            if kind == "/ICCBased":
                return int(cs[1].get("/N", 0)) or None
            if kind in ("/CalRGB",):
                return 3
            if kind in ("/CalGray",):
                return 1
    except Exception:  # noqa: BLE001
        return None
    return None


def _gray_value(values: list[float], n: int) -> float:
    if n == 3:
        return _rgb_gray(*values[:3])
    if n == 4:
        return _cmyk_gray(*values[:4])
    return values[0]


class _Rewriter:
    def __init__(self, pdf: pikepdf.Pdf):
        self.pdf = pdf
        self.done: set[tuple[int, int]] = set()
        self.images: set[tuple[int, int]] = set()

    def content(self, stream_owner, resources) -> bytes:
        cs_map = resources.get("/ColorSpace") if resources is not None else None

        def resolve(name):
            if isinstance(name, pikepdf.Name):
                if str(name) in ("/DeviceRGB", "/DeviceCMYK", "/DeviceGray", "/Pattern"):
                    return name
                if cs_map is not None and name in cs_map:
                    return cs_map[name]
            return name

        out = []
        fill_n = stroke_n = 1
        for instr in pikepdf.parse_content_stream(stream_owner):
            if isinstance(instr, pikepdf.ContentStreamInlineImage):
                out.append(instr)
                continue
            operands, op = list(instr.operands), str(instr.operator)
            try:
                if op in ("rg", "RG"):
                    g = _rgb_gray(*(float(v) for v in operands[:3]))
                    out.append(pikepdf.ContentStreamInstruction([g], Operator("g" if op == "rg" else "G")))
                    continue
                if op in ("k", "K"):
                    g = _cmyk_gray(*(float(v) for v in operands[:4]))
                    out.append(pikepdf.ContentStreamInstruction([g], Operator("g" if op == "k" else "G")))
                    continue
                if op in ("cs", "CS"):
                    n = _components(resolve(operands[0]))
                    if n in (3, 4):
                        out.append(pikepdf.ContentStreamInstruction([Name.DeviceGray], Operator(op)))
                        if op == "cs":
                            fill_n = n
                        else:
                            stroke_n = n
                        continue
                    if op == "cs":
                        fill_n = 1
                    else:
                        stroke_n = 1
                if op in ("sc", "scn", "SC", "SCN"):
                    n = fill_n if op in ("sc", "scn") else stroke_n
                    if n in (3, 4) and len(operands) == n and not any(isinstance(v, pikepdf.Name) for v in operands):
                        numbers = [float(v) for v in operands]
                        out.append(pikepdf.ContentStreamInstruction([_gray_value(numbers, n)], Operator(op)))
                        continue
            except (TypeError, ValueError):
                pass
            out.append(instr)
        return pikepdf.unparse_content_stream(out)

    def resources(self, resources, depth=0) -> None:
        if resources is None or depth > 12:
            return
        xobjects = resources.get("/XObject")
        if xobjects is None:
            return
        for key in list(xobjects.keys()):
            obj = xobjects[key]
            if not isinstance(obj, pikepdf.Stream):
                continue
            subtype = obj.get("/Subtype")
            if subtype == "/Form" and obj.objgen not in self.done:
                self.done.add(obj.objgen)
                try:
                    obj.write(self.content(obj, obj.get("/Resources")))
                except Exception:  # noqa: BLE001 - leave odd forms unchanged
                    pass
                self.resources(obj.get("/Resources"), depth + 1)
            elif subtype == "/Image" and obj.objgen not in self.images:
                self.images.add(obj.objgen)
                self.image(obj)

    def image(self, obj: pikepdf.Stream) -> None:
        cs = obj.get("/ColorSpace")
        if _components(cs) == 1 and not isinstance(cs, pikepdf.Array):
            return
        image = load_image(obj)
        if image is None or image.mode == "L":
            return
        gray = image.convert("L")
        if "/DCTDecode" in filters_of(obj):
            replace_with_jpeg(obj, gray, encode_jpeg(gray, 88))
        else:
            replace_with_flate(obj, gray)

    def page(self, page: pikepdf.Page) -> None:
        resources = page.obj.get("/Resources")
        page.contents_coalesce()
        if "/Contents" in page.obj:
            page.obj.Contents.write(self.content(page, resources))
        self.resources(resources)
        # Annotation appearances (stamps, highlights) as well.
        for annot in page.obj.get("/Annots", []) or []:
            try:
                ap = annot.get("/AP")
                normal = ap.get("/N") if ap is not None else None
                if isinstance(normal, pikepdf.Stream) and normal.objgen not in self.done:
                    self.done.add(normal.objgen)
                    normal.write(self.content(normal, normal.get("/Resources")))
                    self.resources(normal.get("/Resources"))
            except Exception:  # noqa: BLE001
                continue


def run(source: Path, ctx) -> list[Path]:
    method = ctx.options.get("method", "preserve")
    out = ctx.output_path(source, " (grayscale)")
    if method == "rasterize":
        dpi = int(ctx.options.get("dpi", 200))
        doc = open_document(source, ctx.password_for(source))
        result = pikepdf.new()
        try:
            for i in range(len(doc)):
                ctx.progress(i / len(doc), f"Page {i + 1} of {len(doc)}")
                image, scale = render_page(doc, i, dpi, grayscale=True)
                real = scale * 72
                xobj = image_xobject(result, image, quality=80)
                add_image_page(result, xobj, image.width, image.height, (real, real), page_size="fit")
        finally:
            doc.close()
        return [ctx.save_pdf(result, out)]
    pdf = ctx.open_pdf(source)
    rewriter = _Rewriter(pdf)
    indexes = parse_pages("", len(pdf.pages))
    for n, i in enumerate(indexes):
        ctx.progress(0.9 * n / len(indexes), f"Page {i + 1} of {len(indexes)}")
        try:
            rewriter.page(pdf.pages[i])
        except pikepdf.PdfError:
            continue
    ctx.progress(0.92, "Saving")
    return [ctx.save_pdf(pdf, out)]


TOOL = Tool(
    id="grayscale",
    name="Grayscale PDF",
    category=OPTIMIZE,
    description="Convert colour pages to black and white, ready for cheap printing.",
    icon="grayscale",
    run=run,
    chainable=True,
    keywords="black white monochrome gray grey colour",
    options=[
        Choice("method", "Method", "preserve", choices=[
            ("preserve", "Keep text sharp and selectable (recommended)"),
            ("rasterize", "Convert pages to grey images (removes every colour)")],
            help="The first method keeps the document as it is and only changes colours. A few special colours "
                 "(spot colours, gradients) may stay coloured; the second method always removes them."),
        Choice("dpi", "Resolution", 200, choices=[(150, "150 dpi"), (200, "200 dpi"), (300, "300 dpi")],
               visible_when=("method", ("rasterize",))),
    ],
)
