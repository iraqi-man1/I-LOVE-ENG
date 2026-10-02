from __future__ import annotations

from pathlib import Path

import pikepdf

from .base import EDIT, Flag, Text, Tool

FIELDS = [
    ("title", "/Title", "dc:title", "Title"),
    ("author", "/Author", "dc:creator", "Author"),
    ("subject", "/Subject", "dc:description", "Subject"),
    ("keywords", "/Keywords", "pdf:Keywords", "Keywords"),
    ("creator", "/Creator", "xmp:CreatorTool", "Created with"),
    ("producer", "/Producer", "pdf:Producer", "Producer"),
]


def read_metadata(path: str, password: str | None = None) -> dict[str, str]:
    values: dict[str, str] = {}
    with pikepdf.open(path, password=password or "") as pdf:
        info = pdf.docinfo
        for key, pdf_key, _, _ in FIELDS:
            try:
                value = info.get(pdf_key)
                values[key] = str(value) if value is not None else ""
            except Exception:  # noqa: BLE001
                values[key] = ""
    return values


def run(source: Path, ctx) -> list[Path]:
    o = ctx.options
    pdf = ctx.open_pdf(source)
    if o.get("clear_all"):
        try:
            del pdf.Root.Metadata
        except (AttributeError, KeyError):
            pass
        for key in list(pdf.docinfo.keys()):
            del pdf.docinfo[key]
    with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as meta:
        for key, pdf_key, xmp_key, _ in FIELDS:
            value = o.get(key)
            if value is None:
                continue
            value = str(value).strip()
            if value == "" and not o.get("clear_empty"):
                continue
            if value:
                pdf.docinfo[pdf_key] = value
                try:
                    if xmp_key == "dc:creator":
                        meta[xmp_key] = [v.strip() for v in value.split(";") if v.strip()]
                    elif xmp_key == "dc:title" or xmp_key == "dc:description":
                        meta[xmp_key] = value
                    else:
                        meta[xmp_key] = value
                except Exception:  # noqa: BLE001 - XMP is best effort
                    pass
            else:
                if pdf_key in pdf.docinfo:
                    del pdf.docinfo[pdf_key]
                try:
                    if xmp_key in meta:
                        del meta[xmp_key]
                except Exception:  # noqa: BLE001
                    pass
    return [ctx.save_pdf(pdf, ctx.output_path(source, " (metadata)"))]


def prefill(path: str, password: str | None) -> dict:
    try:
        return read_metadata(path, password)
    except Exception:  # noqa: BLE001
        return {}


TOOL = Tool(
    id="metadata",
    name="Edit metadata",
    category=EDIT,
    description="Change the title, author, subject and keywords stored inside a PDF.",
    icon="tag",
    run=run,
    chainable=True,
    prefill=prefill,
    keywords="properties title author keywords info",
    options=[
        *[Text(key, label, None, remember=False) for key, _, _, label in FIELDS],
        Flag("clear_empty", "Remove fields I leave empty", False,
             help="Otherwise empty fields keep their current value. Separate several authors with ;"),
        Flag("clear_all", "Remove all other metadata first", False),
    ],
)
