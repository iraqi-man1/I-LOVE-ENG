"""Opening files and folders with the operating system."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def open_path(path: str) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def reveal(path: str) -> None:
    p = Path(path)
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", str(p)])
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(p)])
            return
    except OSError:
        pass
    open_path(str(p.parent if p.is_file() else p))
