"""Word, Excel and PowerPoint to PDF.

Conversion uses an office suite that is already installed on the computer:
Microsoft Office (Windows) or LibreOffice (Windows and macOS). Both run
locally; nothing is uploaded.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..core.errors import Cancelled, ToolError
from ..core.paths import IS_WINDOWS, find_libreoffice
from .base import CONVERT, EXCEL, POWERPOINT, WORD, Choice, Tool

PROG_IDS = {WORD: "Word.Application", EXCEL: "Excel.Application", POWERPOINT: "PowerPoint.Application"}
APP_NAMES = {WORD: "Word", EXCEL: "Excel", POWERPOINT: "PowerPoint"}


def ms_office_available(kind: str) -> bool:
    if not IS_WINDOWS:
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, PROG_IDS[kind] + "\\CLSID"):
            return True
    except OSError:
        return False


def engines(kind: str) -> list[str]:
    found = []
    if ms_office_available(kind):
        found.append("office")
    if find_libreoffice():
        found.append("libreoffice")
    return found


def _missing_message(kind: str) -> str:
    if IS_WINDOWS:
        return (f"Converting {APP_NAMES[kind]} files needs Microsoft Office or the free LibreOffice "
                "(libreoffice.org) installed on this computer. Install one, then try again.")
    return (f"Converting {APP_NAMES[kind]} files needs the free LibreOffice (libreoffice.org) installed "
            "in Applications. Install it, then try again.")


def _convert_ms_office(kind: str, source: Path, out: Path) -> None:
    import comtypes
    import comtypes.client

    comtypes.CoInitialize()
    app = None
    try:
        app = comtypes.client.CreateObject(PROG_IDS[kind], dynamic=True)
        src, dst = str(source.resolve()), str(out.resolve())
        if kind == WORD:
            app.Visible = False
            app.DisplayAlerts = 0
            doc = app.Documents.Open(src, False, True, False)  # ConfirmConversions, ReadOnly, AddToRecent
            try:
                doc.ExportAsFixedFormat(dst, 17)  # wdExportFormatPDF
            finally:
                doc.Close(0)
        elif kind == EXCEL:
            app.Visible = False
            app.DisplayAlerts = False
            book = app.Workbooks.Open(src, 0, True)  # UpdateLinks, ReadOnly
            try:
                book.ExportAsFixedFormat(0, dst)  # xlTypePDF
            finally:
                book.Close(False)
        else:
            pres = app.Presentations.Open(src, True, False, False)  # ReadOnly, Untitled, WithWindow
            try:
                pres.SaveAs(dst, 32)  # ppSaveAsPDF
            finally:
                pres.Close()
    finally:
        if app is not None:
            try:
                app.Quit()
            except Exception:  # noqa: BLE001
                pass
        comtypes.CoUninitialize()


def _convert_libreoffice(source: Path, out: Path, ctx) -> None:
    soffice = find_libreoffice()
    if not soffice:
        raise ToolError("LibreOffice was not found.")
    work = Path(tempfile.mkdtemp(prefix="pdftoolbox-lo-"))
    try:
        profile = (work / "profile").as_uri()
        cmd = [str(soffice), "--headless", "--norestore", "--nolockcheck", "--nodefault",
               f"-env:UserInstallation={profile}", "--convert-to", "pdf", "--outdir", str(work / "out"), str(source)]
        flags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=flags)
        waited = 0.0
        while proc.poll() is None:
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                waited += 0.5
                try:
                    ctx.check_cancel()
                except Exception:
                    proc.kill()
                    raise
                if waited > 600:
                    proc.kill()
                    raise ToolError("LibreOffice took too long to convert this file.")
        produced = list((work / "out").glob("*.pdf"))
        if not produced:
            output = (proc.stdout.read() if proc.stdout else b"").decode(errors="replace").strip()
            raise ToolError(f"LibreOffice could not convert “{source.name}”. {output[-300:]}")
        shutil.move(str(produced[0]), str(out))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def make_runner(kind: str):
    def run(source: Path, ctx) -> list[Path]:
        available = engines(kind)
        if not available:
            raise ToolError(_missing_message(kind))
        choice = ctx.options.get("engine", "auto")
        order = available if choice == "auto" else [choice] + [e for e in available if e != choice]
        out = ctx.output_path(source, "", ".pdf")
        tmp = out.with_name(f".{out.stem}.part.pdf")
        errors = []
        for engine in order:
            ctx.progress(0.1, f"Converting with {'Microsoft ' + APP_NAMES[kind] if engine == 'office' else 'LibreOffice'}")
            try:
                if engine == "office":
                    _convert_ms_office(kind, source, tmp)
                else:
                    _convert_libreoffice(source, tmp, ctx)
                if tmp.exists() and tmp.stat().st_size > 0:
                    os.replace(tmp, out)
                    return [out]
            except Cancelled:
                raise
            except ToolError as exc:
                errors.append(str(exc))
            except Exception as exc:  # noqa: BLE001 - try the next engine
                errors.append(f"{engine}: {exc}")
            finally:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
        raise ToolError(" ".join(errors) or f"“{source.name}” could not be converted.")

    return run


def _check(kind: str):
    def check():
        return None if engines(kind) else _missing_message(kind)

    return check


def _engine_option():
    return Choice("engine", "Convert with", "auto", choices=[
        ("auto", "Best available"),
        ("office", "Microsoft Office"),
        ("libreoffice", "LibreOffice"),
    ], help="Uses an office suite installed on this computer. Files never leave your device.")


TOOLS = [
    Tool(id="word_to_pdf", name="Word to PDF", category=CONVERT, icon="word",
         description="Convert Word documents (DOC, DOCX, ODT, RTF) to PDF.", inputs=(WORD,),
         run=make_runner(WORD), check=_check(WORD), options=[_engine_option()], keywords="docx doc document"),
    Tool(id="excel_to_pdf", name="Excel to PDF", category=CONVERT, icon="excel",
         description="Convert Excel spreadsheets (XLS, XLSX, ODS, CSV) to PDF.", inputs=(EXCEL,),
         run=make_runner(EXCEL), check=_check(EXCEL), options=[_engine_option()], keywords="xlsx xls spreadsheet"),
    Tool(id="powerpoint_to_pdf", name="PowerPoint to PDF", category=CONVERT, icon="powerpoint",
         description="Convert PowerPoint presentations (PPT, PPTX, ODP) to PDF.", inputs=(POWERPOINT,),
         run=make_runner(POWERPOINT), check=_check(POWERPOINT), options=[_engine_option()],
         keywords="pptx ppt slides presentation"),
]
