"""Helpers for finding and rewriting images inside a PDF."""

from __future__ import annotations

import io
from typing import Callable, Iterator

import pikepdf
from PIL import Image
from pikepdf import Name

from ..core.geometry import page_visible_box


def iter_image_usage(pdf: pikepdf.Pdf) -> dict[tuple[int, int], float]:
    """Map each image object to the longest page side (inches) it appears on."""
    usage: dict[tuple[int, int], float] = {}

    def walk(resources, long_in: float, depth: int = 0) -> None:
        if resources is None or depth > 12:
            return
        xobjects = resources.get("/XObject")
        if xobjects is None:
            return
        for key in list(xobjects.keys()):
            obj = xobjects[key]
            if not isinstance(obj, pikepdf.Stream) or not obj.is_indirect:
                continue
            subtype = obj.get("/Subtype")
            if subtype == "/Image":
                usage[obj.objgen] = max(usage.get(obj.objgen, 0.0), long_in)
            elif subtype == "/Form":
                walk(obj.get("/Resources"), long_in, depth + 1)

    for page in pdf.pages:
        box = page_visible_box(page)
        walk(page.obj.get("/Resources"), max(box.width, box.height) / 72.0)
    return usage


def is_photo(image: Image.Image) -> bool:
    """Guess whether an image is a photo or scan (suits JPEG) or line art."""
    # Sample pixels (no averaging) so texture and noise are preserved.
    small = image.convert("RGB").resize((128, 128), Image.Resampling.NEAREST)
    colors = small.getcolors(maxcolors=600)
    if colors is None:
        return True
    gray = all(r == g == b for _, (r, g, b) in colors)
    return gray and len(colors) > 100


def encode_jpeg(image: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=quality, optimize=True, progressive=False)
    return buf.getvalue()


def replace_with_jpeg(obj: pikepdf.Stream, image: Image.Image, data: bytes) -> None:
    obj.write(data, filter=Name.DCTDecode)
    obj.Width = image.width
    obj.Height = image.height
    obj.ColorSpace = Name.DeviceGray if image.mode == "L" else Name.DeviceRGB
    obj.BitsPerComponent = 8
    for key in ("/DecodeParms", "/Decode"):
        if key in obj:
            del obj[key]


def replace_with_flate(obj: pikepdf.Stream, image: Image.Image) -> None:
    import zlib

    obj.write(zlib.compress(image.tobytes(), 9), filter=Name.FlateDecode)
    obj.Width = image.width
    obj.Height = image.height
    obj.ColorSpace = Name.DeviceGray if image.mode == "L" else Name.DeviceRGB
    obj.BitsPerComponent = 8
    for key in ("/DecodeParms", "/Decode"):
        if key in obj:
            del obj[key]


SKIP_FILTERS = {"/JBIG2Decode", "/CCITTFaxDecode"}


def filters_of(obj: pikepdf.Stream) -> list[str]:
    f = obj.get("/Filter")
    if f is None:
        return []
    if isinstance(f, pikepdf.Array):
        return [str(x) for x in f]
    return [str(f)]


def load_image(obj: pikepdf.Stream) -> Image.Image | None:
    """Decode an image XObject to an RGB or L PIL image, or None if unsuitable."""
    if obj.get("/ImageMask", False) or int(obj.get("/BitsPerComponent", 8)) not in (8,):
        return None
    if any(f in SKIP_FILTERS for f in filters_of(obj)):
        return None
    if "/Decode" in obj:
        return None
    try:
        image = pikepdf.PdfImage(obj).as_pil_image()
    except Exception:  # noqa: BLE001 - unsupported encodings are left alone
        return None
    if image.mode == "CMYK":
        image = image.convert("RGB")
    elif image.mode in ("P", "PA", "LA", "RGBA", "1", "I;16"):
        image = image.convert("L" if image.mode in ("LA", "1", "I;16") else "RGB")
    elif image.mode not in ("L", "RGB"):
        return None
    return image


def walk_images(pdf: pikepdf.Pdf, progress: Callable[[float], None] | None = None
                ) -> Iterator[tuple[pikepdf.Stream, float]]:
    usage = iter_image_usage(pdf)
    total = len(usage)
    for n, (objgen, long_in) in enumerate(usage.items()):
        if progress:
            progress(n / max(1, total))
        try:
            obj = pdf.get_object(objgen)
        except Exception:  # noqa: BLE001
            continue
        yield obj, long_in
