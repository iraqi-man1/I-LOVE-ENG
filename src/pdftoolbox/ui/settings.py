"""Persistent user preferences."""

from __future__ import annotations

import json
import os
from typing import Any

from PySide6.QtCore import QSettings

from pdftoolbox import APP_ID, ORG_NAME


def store() -> QSettings:
    override = os.environ.get("PDFTOOLBOX_SETTINGS_DIR")
    if override:  # used by tests and portable setups
        return QSettings(os.path.join(override, "settings.ini"), QSettings.Format.IniFormat)
    return QSettings(ORG_NAME, APP_ID)


def get(key: str, default: Any = None) -> Any:
    raw = store().value(key)
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def put(key: str, value: Any) -> None:
    store().setValue(key, json.dumps(value))


# Common preferences
def output_mode() -> str:
    return get("output/mode", "same")  # "same" (next to the original) or "folder"


def output_folder() -> str:
    from pathlib import Path

    return get("output/folder", str(Path.home() / "Documents"))


def open_when_done() -> bool:
    return bool(get("output/open_when_done", False))


def auto_update() -> bool:
    return bool(get("updates/auto", True))


def theme() -> str:
    return get("ui/theme", "system")
