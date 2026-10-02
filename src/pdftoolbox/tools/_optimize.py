"""Lossless clean-up shared by Compress and Optimize."""

from __future__ import annotations

import hashlib

import pikepdf
from pikepdf import Name


def dedupe_images(pdf: pikepdf.Pdf) -> int:
    """Point identical image streams at a single copy."""
    canonical: dict[bytes, pikepdf.Object] = {}
    replaced = 0

    def walk(resources, depth=0):
        nonlocal replaced
        if resources is None or depth > 12:
            return
        xobjects = resources.get("/XObject")
        if xobjects is None:
            return
        for key in list(xobjects.keys()):
            obj = xobjects[key]
            if not isinstance(obj, pikepdf.Stream):
                continue
            if obj.get("/Subtype") == "/Form":
                walk(obj.get("/Resources"), depth + 1)
                continue
            if obj.get("/Subtype") != "/Image" or "/SMask" in obj or "/Mask" in obj:
                continue
            try:
                digest = hashlib.sha256(
                    obj.read_raw_bytes() + repr(sorted((str(k), repr(v)) for k, v in obj.items())).encode()
                ).digest()
            except Exception:  # noqa: BLE001
                continue
            first = canonical.setdefault(digest, obj)
            if first.objgen != obj.objgen:
                xobjects[key] = first
                replaced += 1

    for page in pdf.pages:
        walk(page.obj.get("/Resources"))
    return replaced


def clean_document(pdf: pikepdf.Pdf, *, metadata: bool = False, javascript: bool = False,
                   thumbnails: bool = True) -> None:
    for page in pdf.pages:
        try:
            page.remove_unreferenced_resources()
        except Exception:  # noqa: BLE001
            pass
        for key in (("/Thumb",) if thumbnails else ()) + ("/PieceInfo",):
            if key in page.obj:
                del page.obj[key]
    if "/PieceInfo" in pdf.Root:
        del pdf.Root.PieceInfo
    if metadata:
        if "/Metadata" in pdf.Root:
            del pdf.Root.Metadata
        for key in list(pdf.docinfo.keys()):
            del pdf.docinfo[key]
    if javascript:
        names = pdf.Root.get("/Names")
        if names is not None and "/JavaScript" in names:
            del names.JavaScript
        if "/OpenAction" in pdf.Root:
            action = pdf.Root.OpenAction
            if isinstance(action, pikepdf.Dictionary) and action.get("/S") == Name.JavaScript:
                del pdf.Root.OpenAction
        if "/AA" in pdf.Root:
            del pdf.Root.AA
