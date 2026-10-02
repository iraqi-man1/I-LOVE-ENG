"""Light and dark themes (Fusion style with a custom palette and style sheet)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

ACCENT = "#e5533d"

LIGHT = {
    "window": "#f5f6f8", "surface": "#ffffff", "surface2": "#eef0f3", "border": "#dfe2e7", "text": "#1f2329",
    "muted": "#646b75", "accent": ACCENT, "accent_text": "#ffffff", "hover": "#f0f2f5", "selected": "#fde8e4",
    "danger": "#c62828", "success": "#2e7d32", "banner": "#fff4e5",
}
DARK = {
    "window": "#1b1d21", "surface": "#24272c", "surface2": "#2c3036", "border": "#383c43", "text": "#e8eaed",
    "muted": "#a0a6ae", "accent": "#ff6a50", "accent_text": "#ffffff", "hover": "#2f333a", "selected": "#4a2b26",
    "danger": "#ef5350", "success": "#66bb6a", "banner": "#3a3122",
}

current: dict[str, str] = dict(LIGHT)


def is_dark(preference: str) -> bool:
    if preference == "dark":
        return True
    if preference == "light":
        return False
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:  # noqa: BLE001
        return False


def apply(app: QApplication, preference: str = "system") -> None:
    colors = DARK if is_dark(preference) else LIGHT
    current.clear()
    current.update(colors)
    app.setStyle(QStyleFactory.create("Fusion"))
    pal = QPalette()
    c = QColor
    pal.setColor(QPalette.ColorRole.Window, c(colors["window"]))
    pal.setColor(QPalette.ColorRole.WindowText, c(colors["text"]))
    pal.setColor(QPalette.ColorRole.Base, c(colors["surface"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, c(colors["surface2"]))
    pal.setColor(QPalette.ColorRole.Text, c(colors["text"]))
    pal.setColor(QPalette.ColorRole.Button, c(colors["surface"]))
    pal.setColor(QPalette.ColorRole.ButtonText, c(colors["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, c(colors["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, c(colors["accent_text"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, c(colors["surface"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, c(colors["text"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, c(colors["muted"]))
    pal.setColor(QPalette.ColorRole.Link, c(colors["accent"]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, c(colors["muted"]))
    app.setPalette(pal)
    from pdftoolbox.core.paths import resources_dir

    icon_dir = (resources_dir() / "icons").as_posix()
    app.setStyleSheet(STYLE.format(icons=icon_dir, **colors))


STYLE = """
QWidget {{ font-size: 13px; }}
QMainWindow, #Page {{ background: {window}; }}
QToolTip {{ border: 1px solid {border}; padding: 4px; }}

#Sidebar {{ background: {surface}; border-right: 1px solid {border}; }}
#Sidebar QListWidget {{ background: transparent; border: none; outline: none; }}
#Sidebar QListWidget::item {{ padding: 8px 12px; border-radius: 8px; margin: 1px 8px; color: {text}; }}
#Sidebar QListWidget::item:hover {{ background: {hover}; }}
#Sidebar QListWidget::item:selected {{ background: {selected}; color: {accent}; font-weight: 600; }}
#AppTitle {{ font-size: 17px; font-weight: 700; padding: 18px 16px 10px 18px; }}
#SidebarFooter {{ color: {muted}; font-size: 11px; padding: 10px 18px; }}

#Search {{ padding: 8px 12px; border: 1px solid {border}; border-radius: 10px; background: {surface}; min-width: 260px; }}
#Search:focus {{ border-color: {accent}; }}
#PageTitle {{ font-size: 22px; font-weight: 700; }}
#PageSubtitle {{ color: {muted}; font-size: 13px; }}
#SectionTitle {{ font-size: 12px; font-weight: 700; color: {muted}; text-transform: uppercase; letter-spacing: 1px; }}

#ToolCard {{ background: {surface}; border: 1px solid {border}; border-radius: 14px; }}
#ToolCard:hover {{ border-color: {accent}; background: {surface}; }}
#ToolCardTitle {{ font-size: 14px; font-weight: 600; }}
#ToolCardText {{ color: {muted}; font-size: 12px; }}

#Panel {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; }}
#DropZone {{ border: 2px dashed {border}; border-radius: 12px; background: {surface}; color: {muted}; }}
#DropZone[active="true"] {{ border-color: {accent}; background: {selected}; }}

QPushButton {{ padding: 7px 14px; border: 1px solid {border}; border-radius: 8px; background: {surface}; color: {text}; }}
QPushButton:hover {{ background: {hover}; }}
QPushButton:disabled {{ color: {muted}; }}
QPushButton#Primary {{ background: {accent}; color: {accent_text}; border: none; font-weight: 600; padding: 10px 22px; font-size: 14px; }}
QPushButton#Primary:hover {{ background: {accent}; }}
QPushButton#Primary:disabled {{ background: {border}; color: {muted}; }}
QPushButton#Link {{ border: none; background: transparent; color: {accent}; padding: 4px 6px; }}
QPushButton#Link:hover {{ text-decoration: underline; }}
QToolButton {{ border: none; border-radius: 6px; padding: 5px; }}
QToolButton:hover {{ background: {hover}; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    padding: 5px 8px; border: 1px solid {border}; border-radius: 7px; background: {surface}; color: {text};
    selection-background-color: {accent};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {accent}; }}
QLineEdit[invalid="true"] {{ border-color: {danger}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({icons}/arrow-down.svg); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ border: 1px solid {border}; background: {surface}; selection-background-color: {selected};
    selection-color: {text}; outline: none; padding: 4px; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 20px;
    border: none; border-left: 1px solid {border}; border-top-right-radius: 7px; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right;
    width: 20px; border: none; border-left: 1px solid {border}; border-bottom-right-radius: 7px; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover {{ background: {hover}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({icons}/arrow-up.svg); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({icons}/arrow-down.svg); width: 10px; height: 10px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {muted}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: transparent; }}
QListWidget {{ border: 1px solid {border}; border-radius: 10px; background: {surface}; }}
QListWidget::item {{ padding: 4px; }}
QListWidget::item:selected {{ background: {selected}; color: {text}; }}
QProgressBar {{ border: none; border-radius: 4px; background: {surface2}; height: 8px; text-align: center; }}
QProgressBar::chunk {{ border-radius: 4px; background: {accent}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QCheckBox {{ spacing: 8px; }}
#Banner {{ background: {banner}; border: 1px solid {border}; border-radius: 10px; }}
#Muted {{ color: {muted}; }}
#Error {{ color: {danger}; }}
#Success {{ color: {success}; }}
"""
