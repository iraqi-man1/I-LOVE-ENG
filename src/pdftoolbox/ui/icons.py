"""Line icons drawn for this app (24x24, stroke based) and helpers to colour them."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "file": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>',
    "merge": '<rect x="3" y="3" width="8" height="10" rx="1.5"/><rect x="13" y="11" width="8" height="10" rx="1.5"/>'
             '<path d="M11 8h4a2 2 0 0 1 2 2v1"/>',
    "split": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 12h16" stroke-dasharray="2 2"/>'
             '<path d="M9 7h6M9 16h6"/>',
    "extract": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h5"/><path d="M14 3v6h6v3"/>'
               '<path d="M15 18h7M19 15l3 3-3 3"/>',
    "delete": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13"/><path d="M10 11v6M14 11v6"/>',
    "reorder": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
               '<rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "rotate": '<path d="M20 12a8 8 0 1 1-2.34-5.66"/><path d="M20 4v5h-5"/>',
    "rotate_left": '<path d="M4 12a8 8 0 1 0 2.34-5.66"/><path d="M4 4v5h5"/>',
    "crop": '<path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M2 6h14a2 2 0 0 1 2 2v14"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/>'
             '<path d="M21 15l-5-5L5 21"/>',
    "image_pdf": '<rect x="2" y="6" width="12" height="12" rx="1.5"/><path d="M2 15l4-4 4 4"/>'
                 '<path d="M17 4h3a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-3"/><path d="M14 12h5M17 9l3 3-3 3"/>',
    "images": '<rect x="7" y="7" width="14" height="14" rx="2"/><path d="M3 15V5a2 2 0 0 1 2-2h10"/>'
              '<path d="M21 17l-4-4-6 6"/>',
    "word": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M8 11l1.5 6L12 12l2.5 5L16 11"/>',
    "excel": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M9 11l6 7M15 11l-6 7"/>',
    "powerpoint": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>'
                  '<path d="M10 18v-7h2.5a2 2 0 0 1 0 4H10"/>',
    "watermark": '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/>',
    "numbers": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M10 15l2-1.5V19"/>',
    "header": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h8M8 17h8"/><path d="M8 12h8" opacity=".4"/>',
    "tag": '<path d="M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    "lock": '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "unlock": '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.8-1.3"/>',
    "grayscale": '<circle cx="12" cy="12" r="9"/><path d="M12 3v18" /><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor"/>',
    "compress": '<path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7"/>',
    "optimize": '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
    "repair": '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.5-.5-.5-2.5z"/>',
    "ocr": '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"/>'
           '<path d="M8 9h8M8 12h8M8 15h5"/>',
    "batch": '<rect x="7" y="3" width="14" height="14" rx="2"/><path d="M3 7v12a2 2 0 0 0 2 2h12"/><path d="M11 10l2 2 4-4"/>',
    "scan": '<path d="M3 15h18v4a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M5 15V9a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v6"/>'
            '<path d="M7 12h10"/><path d="M8 4h8"/>',
    "back": '<path d="M15 18l-6-6 6-6"/>',
    "add": '<path d="M12 5v14M5 12h14"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
    "up": '<path d="M12 19V5M5 12l7-7 7 7"/>',
    "down": '<path d="M12 5v14M19 12l-7 7-7-7"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    "update": '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/>',
    "open": '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "check": '<path d="M5 12l5 5L20 7"/>',
    "error": '<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5v.5"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
            '<rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
}

CATEGORY_COLORS = {
    "Organize": "#e5533d",
    "Convert": "#2f80ed",
    "Edit": "#8e44ad",
    "Optimize": "#16a085",
    "Security": "#f2994a",
    "Scan": "#0f9d58",
}


def svg(name: str, color: str = "#000000", width: float = 2.0) -> bytes:
    body = _PATHS.get(name, _PATHS["file"]).replace("currentColor", color)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>').encode()


@lru_cache(maxsize=512)
def pixmap(name: str, color: str, size: int, dpr: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg(name, color)))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str = "#555555", size: int = 20) -> QIcon:
    return QIcon(pixmap(name, color, size))


@lru_cache(maxsize=256)
def badge(name: str, background: str, size: int = 44, dpr: float = 2.0) -> QPixmap:
    """A coloured rounded square with a white icon (used on tool cards)."""
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * 0.28, size * 0.28)
    painter.fillPath(path, QColor(background))
    inner = size * 0.56
    offset = (size - inner) / 2
    renderer = QSvgRenderer(QByteArray(svg(name, "#ffffff", 2.0)))
    renderer.render(painter, QRectF(offset, offset, inner, inner))
    painter.end()
    return pm


def app_icon() -> QIcon:
    from pdftoolbox.core.paths import resources_dir

    path = resources_dir() / "icons" / "app.png"
    if path.exists():
        return QIcon(str(path))
    return QIcon(badge("file", "#e5533d", 128))
