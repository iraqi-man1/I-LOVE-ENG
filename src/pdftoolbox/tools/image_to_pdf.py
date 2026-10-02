from __future__ import annotations

import io
import zlib
from pathlib import Path

import pikepdf
from PIL import Image, ImageOps

from ..core.errors import ToolError
from .base import COMBINE, CONVERT, IMAGE, Choice, Number, Tool

MM = 72 / 25.4
PAGE_SIZES = {"a4": (595.276, 841.89), "letter": (612.0, 792.0), "legal": (612.0, 1008.0), "a3": (841.89, 1190.55),
              "a5": (419.528, 595.276)}


def _frames(path: Path):
    try:
        image = Image.open(path)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"“{path.name}” is not an image that can be read ({exc}).") from None
    n = getattr(image, "n_frames", 1)
    for k in range(n):
        if n > 1:
            image.seek(k)
        yield image


def image_xobject(pdf: pikepdf.Pdf, image: Image.Image, raw_jpeg: bytes | None = None, *, quality: int | None = None):
    """Create an image XObject. JPEG files are embedded without re-encoding."""
    if raw_jpeg is not None:
        mode = image.mode
        cs = {"L": pikepdf.Name.DeviceGray, "RGB": pikepdf.Name.DeviceRGB, "CMYK": pikepdf.Name.DeviceCMYK}[mode]
        stream = pikepdf.Stream(pdf, raw_jpeg)
        stream.Type, stream.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
        stream.Width, stream.Height = image.width, image.height
        stream.ColorSpace, stream.BitsPerComponent = cs, 8
        stream.Filter = pikepdf.Name.DCTDecode
        if mode == "CMYK" and "adobe" in image.info:
            stream.Decode = pikepdf.Array([1, 0, 1, 0, 1, 0, 1, 0])
        return stream
    smask = None
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        if alpha.getextrema() != (255, 255):
            smask = pikepdf.Stream(pdf, zlib.compress(alpha.tobytes(), 6))
            smask.Type, smask.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
            smask.Width, smask.Height = alpha.width, alpha.height
            smask.ColorSpace, smask.BitsPerComponent = pikepdf.Name.DeviceGray, 8
            smask.Filter = pikepdf.Name.FlateDecode
        image = rgba.convert("RGB")
    elif image.mode == "1":
        # Black and white: keep 1 bit per pixel, lossless (JPEG would blur the edges).
        stream = pikepdf.Stream(pdf, zlib.compress(image.tobytes(), 9))
        stream.Type, stream.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
        stream.Width, stream.Height = image.width, image.height
        stream.ColorSpace, stream.BitsPerComponent = pikepdf.Name.DeviceGray, 1
        stream.Filter = pikepdf.Name.FlateDecode
        return stream
    elif image.mode not in ("L", "RGB"):
        image = image.convert("RGB")
    if quality:
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=quality, optimize=True)
        data, filt = buf.getvalue(), pikepdf.Name.DCTDecode
    else:
        data, filt = zlib.compress(image.tobytes(), 6), pikepdf.Name.FlateDecode
    stream = pikepdf.Stream(pdf, data)
    stream.Type, stream.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
    stream.Width, stream.Height = image.width, image.height
    stream.ColorSpace = pikepdf.Name.DeviceGray if image.mode == "L" else pikepdf.Name.DeviceRGB
    stream.BitsPerComponent = 8
    stream.Filter = filt
    if smask is not None:
        stream.SMask = smask
    return stream


def add_image_page(pdf: pikepdf.Pdf, xobj, px_w: int, px_h: int, dpi: tuple[float, float], *,
                   page_size: str = "fit", orientation: str = "auto", margin: float = 0.0) -> None:
    dpi_x, dpi_y = dpi
    img_w, img_h = px_w * 72.0 / dpi_x, px_h * 72.0 / dpi_y
    if page_size == "fit":
        page_w, page_h = img_w + 2 * margin, img_h + 2 * margin
    else:
        page_w, page_h = PAGE_SIZES[page_size]
        landscape = img_w > img_h if orientation == "auto" else orientation == "landscape"
        if landscape:
            page_w, page_h = max(page_w, page_h), min(page_w, page_h)
    avail_w, avail_h = page_w - 2 * margin, page_h - 2 * margin
    if page_size == "fit":
        draw_w, draw_h = img_w, img_h
    else:
        scale = min(avail_w / img_w, avail_h / img_h)
        draw_w, draw_h = img_w * scale, img_h * scale
    x = (page_w - draw_w) / 2
    y = (page_h - draw_h) / 2
    page = pdf.add_blank_page(page_size=(page_w, page_h))
    name = page.add_resource(xobj, pikepdf.Name.XObject, prefix="Im")
    page.contents_add(f"q {draw_w:.4f} 0 0 {draw_h:.4f} {x:.4f} {y:.4f} cm {name} Do Q\n".encode())


def _image_dpi(image: Image.Image) -> tuple[float, float]:
    dpi = image.info.get("dpi")
    try:
        x, y = float(dpi[0]), float(dpi[1])
        if 20 <= x <= 4800 and 20 <= y <= 4800:
            return x, y
    except Exception:  # noqa: BLE001
        pass
    return 96.0, 96.0


def images_to_pdf(files: list[Path], out: Path, ctx, *, page_size="fit", orientation="auto", margin=0.0,
                  quality: int | None = None) -> Path:
    pdf = pikepdf.new()
    for n, path in enumerate(files):
        ctx.progress(n / max(1, len(files)), f"Adding {path.name}")
        for frame in _frames(path):
            # Respect the camera's orientation flag.
            try:
                orientation_tag = frame.getexif().get(0x0112, 1) or 1
            except Exception:  # noqa: BLE001
                orientation_tag = 1
            image = ImageOps.exif_transpose(frame) if orientation_tag != 1 else frame
            raw = None
            if (frame.format == "JPEG" and orientation_tag == 1 and frame.mode in ("L", "RGB", "CMYK")
                    and not quality and getattr(frame, "n_frames", 1) == 1):
                raw = path.read_bytes()
            xobj = image_xobject(pdf, image, raw, quality=quality)
            add_image_page(pdf, xobj, image.width, image.height, _image_dpi(frame),
                           page_size=page_size, orientation=orientation, margin=margin)
    ctx.progress(0.95, "Saving")
    return ctx.save_pdf(pdf, out)


def run(files: list[Path], ctx) -> list[Path]:
    opts = ctx.options
    margin = float(opts.get("margin", 0)) * MM
    kwargs = dict(page_size=opts.get("page_size", "a4"), orientation=opts.get("orientation", "auto"), margin=margin,
                  quality=None if opts.get("compression", "original") == "original" else int(opts.get("compression")))
    if opts.get("output", "single") == "each":
        outputs = []
        for n, path in enumerate(files):
            ctx.set_file(n, len(files))
            outputs.append(images_to_pdf([path], ctx.output_path(path, ""), ctx, **kwargs))
        return outputs
    return [images_to_pdf(files, ctx.combined_output_path("images", ".pdf"), ctx, **kwargs)]


TOOL = Tool(
    id="image_to_pdf",
    name="JPG/PNG to PDF",
    category=CONVERT,
    description="Turn photos and images into a PDF, one image per page.",
    icon="image_pdf",
    inputs=(IMAGE,),
    mode=COMBINE,
    output_name="images",
    run=run,
    keywords="jpeg png tiff photo picture convert",
    options=[
        Choice("page_size", "Page size", "a4", choices=[("fit", "Same as image"), ("a4", "A4"), ("letter", "Letter"),
                                                        ("legal", "Legal"), ("a3", "A3"), ("a5", "A5")]),
        Choice("orientation", "Orientation", "auto", choices=[("auto", "Automatic"), ("portrait", "Portrait"),
                                                              ("landscape", "Landscape")],
               visible_when=("page_size", ("a4", "letter", "legal", "a3", "a5"))),
        Number("margin", "Margin", 0, maximum=100, suffix=" mm"),
        Choice("compression", "Image quality", "original", choices=[
            ("original", "Original (no quality loss)"), (90, "High (JPG 90%)"), (75, "Medium (JPG 75%)"),
            (55, "Small file (JPG 55%)")]),
        Choice("output", "Output", "single", choices=[("single", "One PDF with every image"),
                                                      ("each", "One PDF per image")]),
    ],
)
