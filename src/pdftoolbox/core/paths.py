"""Locations of bundled resources, helper programs and user data."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from pdftoolbox import APP_ID

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
FROZEN = getattr(sys, "frozen", False)


def bundle_dir() -> Path:
    """Folder that holds the application's bundled files."""
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def resources_dir() -> Path:
    if FROZEN:
        return bundle_dir() / "pdftoolbox" / "resources"
    return Path(__file__).resolve().parents[1] / "resources"


def user_data_dir() -> Path:
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif IS_MAC:
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    path = base / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_tessdata_dir() -> Path:
    path = user_data_dir() / "tessdata"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _exe(name: str) -> str:
    return name + ".exe" if IS_WINDOWS else name


def bundled_tesseract_dir() -> Path:
    return bundle_dir() / "tesseract"


def find_tesseract() -> Path | None:
    override = os.environ.get("PDFTOOLBOX_TESSERACT")
    if override and Path(override).exists():
        return Path(override)
    bundled = bundled_tesseract_dir() / _exe("tesseract")
    if bundled.exists():
        return bundled
    found = shutil.which("tesseract")
    if found:
        return Path(found)
    candidates = []
    if IS_WINDOWS:
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            root = os.environ.get(env)
            if root:
                candidates.append(Path(root) / "Tesseract-OCR" / "tesseract.exe")
                candidates.append(Path(root) / "Programs" / "Tesseract-OCR" / "tesseract.exe")
    elif IS_MAC:
        candidates += [Path("/opt/homebrew/bin/tesseract"), Path("/usr/local/bin/tesseract")]
    return next((c for c in candidates if c.exists()), None)


def tessdata_dirs() -> list[Path]:
    """Folders that may contain *.traineddata files, most preferred first."""
    dirs: list[Path] = [user_tessdata_dir()]
    env = os.environ.get("TESSDATA_PREFIX")
    if env:
        dirs.append(Path(env))
        dirs.append(Path(env) / "tessdata")
    bundled = bundled_tesseract_dir() / "tessdata"
    dirs.append(bundled)
    exe = find_tesseract()
    if exe:
        dirs.append(exe.parent / "tessdata")
        dirs.append(exe.parent.parent / "share" / "tessdata")
        dirs.append(exe.parent.parent / "share" / "tesseract-ocr" / "5" / "tessdata")
    for p in ("/usr/share/tesseract-ocr/5/tessdata", "/usr/share/tesseract-ocr/4.00/tessdata",
              "/usr/share/tessdata", "/opt/homebrew/share/tessdata", "/usr/local/share/tessdata"):
        dirs.append(Path(p))
    seen, result = set(), []
    for d in dirs:
        if d not in seen and d.is_dir():
            seen.add(d)
            result.append(d)
    return result


def find_libreoffice() -> Path | None:
    override = os.environ.get("PDFTOOLBOX_SOFFICE")
    if override and Path(override).exists():
        return Path(override)
    candidates: list[Path] = []
    if IS_WINDOWS:
        for env in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.environ.get(env)
            if root:
                candidates.append(Path(root) / "LibreOffice" / "program" / "soffice.exe")
    elif IS_MAC:
        candidates += [
            Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
            Path.home() / "Applications/LibreOffice.app/Contents/MacOS/soffice",
        ]
    for c in candidates:
        if c.exists():
            return c
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None
