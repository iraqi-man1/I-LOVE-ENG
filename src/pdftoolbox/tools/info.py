from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

import pikepdf

from ..core.geometry import page_visible_box
from .base import EDIT, Tool

PAPER = {(595, 842): "A4", (612, 792): "Letter", (612, 1008): "Legal", (842, 1191): "A3", (420, 595): "A5",
         (499, 709): "B5", (729, 1032): "B4"}


def _paper(w: float, h: float) -> str:
    key = (round(min(w, h)), round(max(w, h)))
    for (pw, ph), name in PAPER.items():
        if abs(pw - key[0]) <= 2 and abs(ph - key[1]) <= 2:
            return f"{name} {'landscape' if w > h else 'portrait'}"
    return f"{w / 72 * 25.4:.0f} × {h / 72 * 25.4:.0f} mm"


def _size(n: int) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def describe(source: Path, ctx) -> str:
    pdf = ctx.open_pdf(source)
    lines = [f"File: {source.name}", f"Location: {source.parent}", f"Size: {_size(os.path.getsize(source))}",
             f"PDF version: {pdf.pdf_version}", f"Pages: {len(pdf.pages)}"]
    sizes = Counter()
    fonts: set[str] = set()
    image_count = 0
    seen = set()
    for n, page in enumerate(pdf.pages):
        box = page_visible_box(page)
        sizes[_paper(box.width, box.height)] += 1
        res = page.obj.get("/Resources")
        if res is not None:
            for font in (res.get("/Font") or {}).values():
                try:
                    base = str(font.get("/BaseFont", "")).lstrip("/")
                    if base:
                        fonts.add(base.split("+", 1)[-1])
                except Exception:  # noqa: BLE001
                    pass
            for xobj in (res.get("/XObject") or {}).values():
                try:
                    if xobj.get("/Subtype") == "/Image" and xobj.objgen not in seen:
                        seen.add(xobj.objgen)
                        image_count += 1
                except Exception:  # noqa: BLE001
                    pass
        if n % 200 == 0:
            ctx.progress(n / max(1, len(pdf.pages)))
    lines.append("Page sizes: " + ", ".join(f"{name} ({count})" for name, count in sizes.most_common()))
    lines.append("")
    info = pdf.docinfo
    for key, label in (("/Title", "Title"), ("/Author", "Author"), ("/Subject", "Subject"), ("/Keywords", "Keywords"),
                       ("/Creator", "Created with"), ("/Producer", "Producer"), ("/CreationDate", "Created"),
                       ("/ModDate", "Modified")):
        try:
            value = info.get(key)
        except Exception:  # noqa: BLE001
            value = None
        if value is not None and str(value).strip():
            text = str(value)
            if key.endswith("Date") and text.startswith("D:") and len(text) >= 10:
                text = f"{text[2:6]}-{text[6:8]}-{text[8:10]}" + (f" {text[10:12]}:{text[12:14]}" if len(text) >= 14 else "")
            lines.append(f"{label}: {text}")
    lines.append("")
    lines.append(f"Password protected: {'yes' if pdf.is_encrypted else 'no'}")
    if pdf.is_encrypted:
        enc = pdf.encryption
        lines.append(f"Encryption: {enc.stream_method.name if hasattr(enc, 'stream_method') else 'yes'} "
                     f"({enc.bits} bit)")
        allow = pdf.allow
        lines.append("Allowed: " + ", ".join(name for name, ok in (
            ("printing", allow.print_highres or allow.print_lowres), ("copying text", allow.extract),
            ("editing", allow.modify_other), ("comments", allow.modify_annotation),
            ("form filling", allow.modify_form)) if ok) or "nothing")
    root = pdf.Root
    acro = root.get("/AcroForm")
    fields = len(acro.get("/Fields", [])) if acro is not None else 0
    lines.append(f"Form fields: {fields}")
    has_sig = False
    if acro is not None:
        try:
            has_sig = any(f.get("/FT") == "/Sig" for f in acro.get("/Fields", []))
        except Exception:  # noqa: BLE001
            pass
    lines.append(f"Digital signatures: {'yes' if has_sig else 'no'}")
    lines.append(f"Bookmarks: {'yes' if root.get('/Outlines') is not None else 'no'}")
    names = root.get("/Names")
    has_js = bool(names is not None and names.get("/JavaScript") is not None) or root.get("/OpenAction") is not None
    lines.append(f"JavaScript or open actions: {'yes' if has_js else 'no'}")
    lines.append(f"Attachments: {len(pdf.attachments)}")
    lines.append(f"Tagged (accessible): {'yes' if root.get('/MarkInfo', {}).get('/Marked', False) else 'no'}")
    lines.append(f"Fast web view (linearized): {'yes' if pdf.is_linearized else 'no'}")
    lines.append(f"Images: {image_count}")
    if fonts:
        lines.append(f"Fonts ({len(fonts)}): " + ", ".join(sorted(fonts)[:40]) + (" ..." if len(fonts) > 40 else ""))
    else:
        lines.append("Fonts: none (the pages may be scanned images; use OCR to make them searchable)")
    return "\n".join(lines)


def run(source: Path, ctx):
    return {"report": describe(source, ctx)}


TOOL = Tool(
    id="info",
    name="PDF information",
    category=EDIT,
    description="See page count, page sizes, fonts, security and other details of a PDF.",
    icon="info",
    run=run,
    report=True,
    keywords="details properties inspect fonts version",
)
