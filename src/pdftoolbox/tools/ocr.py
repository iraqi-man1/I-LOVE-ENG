"""OCR: add an invisible, searchable text layer to scanned pages.

Each page is rendered with PDFium and read by Tesseract, which produces a
text-only PDF page. That page is placed over the original, so the document
looks exactly the same but text can be searched, selected and copied.
"""

from __future__ import annotations

import os
import subprocess
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import pikepdf

from ..core import stamp
from ..core.errors import ToolError
from ..core.pages import parse_pages
from ..core.paths import IS_WINDOWS, find_tesseract, tessdata_dirs
from ..core.render import open_document, render_page
from .base import EDIT, Choice, Flag, Languages, Pages, Tool

LANGUAGE_NAMES = {
    "eng": "English", "ara": "Arabic", "fra": "French", "deu": "German", "spa": "Spanish", "ita": "Italian",
    "por": "Portuguese", "nld": "Dutch", "tur": "Turkish", "fas": "Persian", "urd": "Urdu", "kur": "Kurdish",
    "ckb": "Kurdish (Sorani)", "kmr": "Kurdish (Kurmanji)", "heb": "Hebrew", "rus": "Russian", "ukr": "Ukrainian",
    "pol": "Polish", "ces": "Czech", "ell": "Greek", "hin": "Hindi", "ben": "Bengali", "chi_sim": "Chinese (Simplified)",
    "chi_tra": "Chinese (Traditional)", "jpn": "Japanese", "kor": "Korean", "vie": "Vietnamese", "ind": "Indonesian",
    "msa": "Malay", "tha": "Thai", "swe": "Swedish", "nor": "Norwegian", "dan": "Danish", "fin": "Finnish",
    "hun": "Hungarian", "ron": "Romanian", "bul": "Bulgarian", "syr": "Syriac",
}


def installed_languages() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for folder in tessdata_dirs():
        for file in sorted(folder.glob("*.traineddata")):
            code = file.stem
            if code in ("osd", "equ") or code in found:
                continue
            found[code] = folder
    return found


def language_choices() -> list[tuple[str, str]]:
    return [(code, LANGUAGE_NAMES.get(code, code)) for code in installed_languages()]


def check() -> str | None:
    if not find_tesseract():
        return ("The OCR engine (Tesseract) was not found. It is included with the installed app; "
                "if you are running from source, install Tesseract first.")
    if not installed_languages():
        return "No OCR languages are installed."
    return None


def _tessdata_for(langs: list[str]) -> Path:
    installed = installed_languages()
    missing = [code for code in langs if code not in installed]
    if missing:
        raise ToolError("These OCR languages are not installed: " + ", ".join(missing))
    for folder in tessdata_dirs():
        if all((folder / f"{code}.traineddata").exists() for code in langs):
            return folder
    raise ToolError("The selected OCR languages are installed in different folders. "
                    "Copy them into one folder: " + str(tessdata_dirs()[0]))


def _page_has_text(doc, index: int) -> bool:
    page = doc[index]
    try:
        text = page.get_textpage()
        try:
            return text.count_chars() > 25
        finally:
            text.close()
    finally:
        page.close()


def _run_tesseract(exe: Path, image: Path, base: Path, langs: str, dpi: int, tessdata: Path,
                   want_text: bool) -> None:
    cmd = [str(exe), str(image), str(base), "-l", langs, "--dpi", str(dpi), "--tessdata-dir", str(tessdata),
           "-c", "textonly_pdf=1", "pdf"]
    if want_text:
        cmd.append("txt")
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    flags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
    proc = subprocess.run(cmd, capture_output=True, env=env, creationflags=flags, timeout=900)
    if proc.returncode != 0 or not base.with_suffix(".pdf").exists():
        raise ToolError("OCR failed: " + proc.stderr.decode(errors="replace").strip()[-400:])


def run(source: Path, ctx) -> list[Path]:
    exe = find_tesseract()
    if not exe:
        raise ToolError(check() or "Tesseract was not found.")
    o = ctx.options
    langs = o.get("languages") or ["eng"]
    if isinstance(langs, str):
        langs = [code for code in langs.replace(",", "+").split("+") if code]
    tessdata = _tessdata_for(langs)
    dpi = int(o.get("dpi", 300))
    want_text = bool(o.get("text_file", False))
    doc = open_document(source, ctx.password_for(source))
    pdf = ctx.open_pdf(source)
    indexes = parse_pages(o.get("pages") or "", len(pdf.pages))
    skip_existing = o.get("existing", "skip") == "skip"
    work = ctx.temp_dir / "ocr"
    work.mkdir(exist_ok=True)
    workers = max(1, min(int(o.get("threads", 0)) or (os.cpu_count() or 2) - 1, 8))
    todo = []
    skipped = 0
    for i in indexes:
        if skip_existing and _page_has_text(doc, i):
            skipped += 1
        else:
            todo.append(i)
    results: dict[int, Path] = {}
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending: dict = {}

            def finish(futures) -> None:
                for future in futures:
                    i = pending.pop(future)
                    future.result()
                    results[i] = work / f"p{i}.pdf"
                    (work / f"p{i}.png").unlink(missing_ok=True)
                ctx.progress(0.05 + 0.85 * len(results) / max(1, len(todo)),
                             f"Recognised {len(results)} of {len(todo)} pages")

            try:
                for i in todo:
                    ctx.check_cancel()
                    # Keep a bounded number of rendered pages waiting on disk.
                    while len(pending) >= workers * 2:
                        finish(wait(pending, return_when=FIRST_COMPLETED).done)
                    image, scale = render_page(doc, i, dpi, grayscale=True, annotations=False)
                    png = work / f"p{i}.png"
                    real_dpi = max(1, round(scale * 72))
                    image.save(png, "PNG", dpi=(real_dpi, real_dpi))
                    del image
                    future = pool.submit(_run_tesseract, exe, png, work / f"p{i}", "+".join(langs), real_dpi,
                                         tessdata, want_text)
                    pending[future] = i
                    finish([f for f in list(pending) if f.done()])
                while pending:
                    ctx.check_cancel()
                    finish(wait(pending, timeout=0.5, return_when=FIRST_COMPLETED).done)
            except BaseException:
                for future in pending:
                    future.cancel()
                raise
    finally:
        doc.close()
    ctx.progress(0.92, "Adding the text layer")
    texts = []
    for i in sorted(results):
        with pikepdf.open(results[i]) as layer:
            form = pdf.copy_foreign(layer.pages[0].as_form_xobject())
        stamp.place_form(pdf.pages[i], form)
        if want_text:
            txt = results[i].with_suffix(".txt")
            if txt.exists():
                texts.append(txt.read_text(encoding="utf-8", errors="replace"))
    out = ctx.output_path(source, " (searchable)")
    ctx.save_pdf(pdf, out)
    outputs = [out]
    if want_text:
        txt_path = out.with_suffix(".txt")
        txt_path.write_text("\f".join(texts), encoding="utf-8")
        outputs.append(txt_path)
    if skipped:
        ctx.note(f"{skipped} page{'s' if skipped != 1 else ''} already had text and {'were' if skipped != 1 else 'was'} "
                 "left as is.")
    return outputs


TOOL = Tool(
    id="ocr",
    name="OCR (searchable PDF)",
    category=EDIT,
    description="Recognise text in scanned pages so you can search, select and copy it.",
    icon="ocr",
    run=run,
    chainable=True,
    check=check,
    keywords="scan recognise recognize text searchable tesseract",
    options=[
        Languages("languages", "Document languages", ["eng"],
                  help="Choose every language that appears in the document. Fewer languages is faster."),
        Choice("existing", "Pages that already have text", "skip", choices=[
            ("skip", "Leave them as they are"), ("all", "Recognise them too")]),
        Choice("dpi", "Accuracy", 300, choices=[(200, "Fast (200 dpi)"), (300, "Recommended (300 dpi)"),
                                                (400, "Small print (400 dpi)")]),
        Flag("text_file", "Also save the recognised text as a .txt file", False),
        Pages("pages", "Pages", ""),
    ],
)
