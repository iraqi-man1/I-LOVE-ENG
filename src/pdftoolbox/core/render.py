"""Rendering pages to images with PDFium."""

from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium

from .errors import PasswordRequired, ToolError


def open_document(path: Path, password: str | None = None) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(str(path), password=password or None)
    except pdfium.PdfiumError as exc:
        message = str(exc).lower()
        if "password" in message:
            raise PasswordRequired(Path(path).name) from None
        raise ToolError(f"“{Path(path).name}” could not be opened ({exc}).") from None


def render_page(doc: pdfium.PdfDocument, index: int, dpi: float, *, grayscale: bool = False,
                annotations: bool = True, max_pixels: int = 80_000_000):
    """Render one page to a PIL image. Very large renders are scaled down."""
    page = doc[index]
    try:
        w, h = page.get_size()
        scale = dpi / 72.0
        pixels = (w * scale) * (h * scale)
        if pixels > max_pixels:
            scale *= (max_pixels / pixels) ** 0.5
        bitmap = page.render(scale=scale, grayscale=grayscale, draw_annots=annotations,
                             may_draw_forms=annotations)
        image = bitmap.to_pil()
        if grayscale and image.mode != "L":
            image = image.convert("L")
        elif image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        return image, scale
    finally:
        page.close()
