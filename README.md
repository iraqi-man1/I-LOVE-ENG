# PDF Toolbox

A native desktop app for Windows and macOS that does everyday PDF jobs on your own computer. It works offline: no
accounts, subscriptions, cloud processing or uploads. Files never leave the device.

## Tools

| Organize | Convert | Edit | Optimize | Security |
| --- | --- | --- | --- | --- |
| Merge PDF | PDF to JPG/PNG | Watermark (text or image) | Compress PDF | Protect with a password |
| Split PDF (pages, every N, parts, ranges, bookmarks) | JPG/PNG to PDF | Page numbers | Optimize PDF (lossless, fast web view) | Remove a known password |
| Extract pages | Extract images | Header and footer | Grayscale PDF | |
| Delete pages | Word to PDF | Edit metadata | Repair PDF | |
| Reorder pages (drag and drop) | Excel to PDF | PDF information | Batch processing | |
| Rotate PDF | PowerPoint to PDF | OCR (searchable PDF) | | |
| Crop PDF (margins or auto-trim) | | | | |

**Scan to PDF**: finds the scanners and multifunction printers connected to the computer, scans one page at a time
from the glass or every page from the document feeder (one or both sides), shows the pages so you can reorder, rotate
or remove them, then saves them as one PDF, optionally with OCR so the text is searchable.

**Batch processing**: build a chain of steps (for example *Rotate → Page numbers → Compress → Protect*) and run it on
hundreds of files. Every tool also accepts many files or a whole folder at once.

**Updates**: when the computer is online the app checks this repository's GitHub releases, shows a notice when a new
version is out, and downloads, verifies (SHA-256) and installs it from inside the app. Without internet everything
else works normally.

## Install

Download the latest installer from the [Releases page](https://github.com/iraqi-man1/I-LOVE-ENG/releases):

* **Windows 10/11:** `PDFToolbox-<version>-windows-x64-setup.exe`. It installs for the current user without
  administrator rights.
* **macOS:** `PDFToolbox-<version>-macos-arm64.dmg` for Apple silicon (M1 and later, macOS 14+) or
  `PDFToolbox-<version>-macos-x64.dmg` for Intel Macs (macOS 15+). Open it and drag the app into Applications.

The installers are not code-signed yet, so the first launch shows a warning:

* Windows SmartScreen: click **More info → Run anyway**.
* macOS: open the app once, then go to **System Settings → Privacy & Security** and click **Open Anyway**.

Signing certificates (a Windows code-signing certificate and an Apple Developer ID) remove these warnings; see
[Releasing](#releasing).

### What each feature needs

| Feature | Needs |
| --- | --- |
| Every PDF tool, OCR (English and Arabic included) | Nothing extra, all bundled |
| Scan to PDF | The scanner's normal driver. Windows uses WIA; macOS uses Image Capture, which also supports network and AirPrint/AirScan scanners without drivers |
| Word, Excel, PowerPoint to PDF | Microsoft Office (Windows) or the free [LibreOffice](https://www.libreoffice.org/download/) (Windows and macOS) installed on the computer |
| More OCR languages | Copy the `.traineddata` file from [tesseract-ocr/tessdata](https://github.com/tesseract-ocr/tessdata) (with `eng.traineddata`) into the folder opened by **Settings → Open OCR languages folder** |

## How it is built

| Part | Library | Licence |
| --- | --- | --- |
| Interface | Qt 6 via PySide6 | LGPL-3.0 |
| Page editing, encryption, repair, compression | pikepdf on qpdf | MPL-2.0 / Apache-2.0 |
| Rendering, thumbnails, PDF to image | PDFium via pypdfium2 | Apache-2.0 / BSD-3 |
| Text, watermarks, page numbers (all scripts, including Arabic) | Qt's PDF writer | LGPL-3.0 |
| OCR | Tesseract | Apache-2.0 |
| Images | Pillow | MIT-CMU |
| Scanning | WIA (Windows), ImageCaptureCore via PyObjC (macOS) | system / MIT |
| Installers | PyInstaller, Inno Setup, hdiutil | GPL with bootloader exception / Inno licence |

MuPDF/PyMuPDF and Ghostscript were deliberately avoided: they are AGPL, which would force the whole app to be
released under the AGPL. Every component above allows a free or commercial app. See
[THIRD_PARTY_NOTICES.txt](src/pdftoolbox/resources/THIRD_PARTY_NOTICES.txt).

### Why it stays responsive with large files

Every job runs in a separate worker process. The window never waits on PDF processing, a job can be cancelled at any
time, and if a damaged file crashes a PDF engine only that job fails; the app keeps running. pikepdf and PDFium load
pages on demand, page thumbnails are rendered in the background only for the pages on screen, OCR runs several pages in
parallel, and results are written to a temporary file and moved into place only when complete. In batch jobs a
problem with one file is reported and the rest carry on.

### Project layout

```
src/pdftoolbox/
  core/        job runner, page ranges, geometry, stamping, rendering, paths
  tools/       one module per tool (merge.py, split.py, ocr.py, ...)
  scan/        scanner back-ends: wia.py (Windows), ica.py (macOS), sane.py, fake.py
  updater/     GitHub release check, download with checksum, installer launch
  ui/          main window, tool screen, scan screen, dialogs, theme
packaging/     PyInstaller spec, Inno Setup script, icons
scripts/       Tesseract bundling, disk image, icons, screenshots
tests/         tool, updater and interface tests
```

### Adding a tool

Create a module in `src/pdftoolbox/tools/`, describe the tool and its options, and list it in `TOOL_MODULES` in
`tools/__init__.py`. The settings form, file list, progress, cancellation, batch support and output naming come for
free:

```python
from pathlib import Path

from .base import EDIT, Flag, Tool


def run(source: Path, ctx) -> list[Path]:
    pdf = ctx.open_pdf(source)            # handles passwords and damaged files
    ...                                   # change the document with pikepdf
    ctx.progress(0.5, "Halfway")          # progress bar and cancel button
    return [ctx.save_pdf(pdf, ctx.output_path(source, " (changed)"))]


TOOL = Tool(id="my_tool", name="My tool", category=EDIT, description="What it does.", run=run,
            chainable=True,  # can be a Batch processing step
            options=[Flag("example", "An example switch", True)])
```

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest                          # tests (OCR test needs Tesseract installed)
PYTHONPATH=src python -m pdftoolbox       # run the app
PDFTOOLBOX_FAKE_SCANNER=1 PYTHONPATH=src python -m pdftoolbox   # try Scan to PDF without a scanner
```

Build an installer locally: run `scripts/fetch_tesseract_windows.ps1` or `scripts/fetch_tesseract_macos.sh`, then
`pyinstaller --noconfirm packaging/pdftoolbox.spec`, then `iscc packaging\windows\installer.iss` (Windows) or
`scripts/make_dmg.sh <version> <arch>` (macOS). The packaged app can check itself with
`"PDF Toolbox" --self-test report.txt`.

## Releasing

1. Change `__version__` in `src/pdftoolbox/__init__.py` (for example to `0.2.0`) and merge it to `main`.
2. Tag that commit and push the tag: `git tag v0.2.0 && git push origin v0.2.0`.
3. The **Build** workflow tests the code, builds and self-tests the Windows installer and both macOS disk images,
   then publishes a GitHub release with the files and `SHA256SUMS.txt`.
4. Installed copies see the new version the next time they check and offer to install it.

Every pull request also builds the installers; download them from the workflow run's *Artifacts* to try a change
before releasing it.

Code signing is optional. To add it later: for macOS, import a Developer ID certificate in the macOS job, pass
`codesign_identity` to PyInstaller, then notarize the disk image with `xcrun notarytool`; for Windows, sign the exe and
installer with `signtool` (or Azure Trusted Signing) before uploading.
