from __future__ import annotations

from pathlib import Path

import pikepdf

from ..core.errors import PasswordRequired, ToolError
from .base import OPTIMIZE, Tool


def _verify(path: Path, password: str | None) -> int:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path), password=password or None)
    try:
        count = len(doc)
        for i in range(count):
            doc[i].close()
        return count
    finally:
        doc.close()


def run(source: Path, ctx) -> list[Path]:
    out = ctx.output_path(source, " (repaired)")
    password = ctx.password_for(source)
    errors = []
    # 1. qpdf: rebuilds broken cross-reference tables and streams.
    try:
        ctx.progress(0.1, "Rebuilding the file structure")
        with pikepdf.open(source, password=password or "", attempt_recovery=True) as pdf:
            warnings = pdf.get_warnings() if hasattr(pdf, "get_warnings") else []
            if len(pdf.pages) == 0:
                raise ToolError("no pages could be recovered")
            ctx.save_pdf(pdf, out, encryption=False)
        pages = _verify(out, None)
        if warnings:
            ctx.note(f"Fixed {len(warnings)} problem{'s' if len(warnings) != 1 else ''} in the file structure; "
                     f"{pages} page{'s' if pages != 1 else ''} recovered.")
        else:
            ctx.note(f"No structural damage was found; the file was rewritten cleanly ({pages} pages).")
        return [out]
    except pikepdf.PasswordError:
        raise PasswordRequired(source.name) from None
    except Exception as exc:  # noqa: BLE001
        errors.append(f"structure rebuild: {exc}")
    # 2. PDFium: a different parser that tolerates other kinds of damage.
    try:
        import pypdfium2 as pdfium

        ctx.progress(0.5, "Trying a second recovery method")
        doc = pdfium.PdfDocument(str(source), password=password or None)
        try:
            tmp = ctx.temp_dir / "pdfium.pdf"
            doc.save(str(tmp))
        finally:
            doc.close()
        with pikepdf.open(tmp, attempt_recovery=True) as pdf:
            ctx.save_pdf(pdf, out, encryption=False)
        pages = _verify(out, None)
        ctx.note(f"Recovered {pages} page{'s' if pages != 1 else ''} with the second recovery method.")
        return [out]
    except Exception as exc:  # noqa: BLE001
        errors.append(f"second method: {exc}")
    raise ToolError("This file is too damaged to repair. " + "; ".join(errors))


TOOL = Tool(
    id="repair",
    name="Repair PDF",
    category=OPTIMIZE,
    description="Try to fix a damaged PDF that won't open or shows errors.",
    icon="repair",
    run=run,
    chainable=True,
    keywords="fix broken corrupt damaged recover",
)
