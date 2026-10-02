"""Reusable widgets: flow layout, file list, option form."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QPoint, QRect, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLayout, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QSizePolicy, QSpinBox,
    QStackedLayout, QToolButton, QVBoxLayout, QWidget,
)

from pdftoolbox.tools import base as tb

from . import icons, theme


class FlowLayout(QLayout):
    """Lays widgets out left to right, wrapping onto new rows."""

    def __init__(self, parent=None, spacing=14):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):  # noqa: N802
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, width):  # noqa: N802
        return self._layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._layout(rect, False)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _layout(self, rect, test):
        x, y, line_height = rect.x(), rect.y(), 0
        visible = [i for i in self._items if not i.widget() or not i.widget().isHidden()]
        for item in visible:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > rect.right() and line_height > 0:
                x, y = rect.x(), y + line_height + self._spacing
                next_x = x + hint.width() + self._spacing
                line_height = 0
            if not test:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


# ----------------------------------------------------------------------------
# File list
# ----------------------------------------------------------------------------


class _InfoSignals(QObject):
    done = Signal(str, object)


class _InfoTask(QRunnable):
    def __init__(self, path: str, signals: _InfoSignals):
        super().__init__()
        self.path, self.signals = path, signals

    def run(self):
        info: dict[str, Any] = {"size": 0}
        try:
            info["size"] = os.path.getsize(self.path)
            if self.path.lower().endswith(".pdf"):
                import pikepdf

                try:
                    with pikepdf.open(self.path) as pdf:
                        info["pages"] = len(pdf.pages)
                        info["restricted"] = pdf.is_encrypted
                except pikepdf.PasswordError:
                    info["locked"] = True
                except Exception as exc:  # noqa: BLE001
                    info["error"] = "Damaged or not a PDF" if "pdf" in str(exc).lower() else str(exc)[:80]
            elif self.path.lower().endswith(tb.EXTENSIONS[tb.IMAGE]):
                from PIL import Image

                with Image.open(self.path) as im:
                    info["dims"] = im.size
                    info["frames"] = getattr(im, "n_frames", 1)
        except Exception as exc:  # noqa: BLE001
            info["error"] = str(exc)[:80]
        self.signals.done.emit(self.path, info)


ROLE_PATH = Qt.ItemDataRole.UserRole
ROLE_INFO = Qt.ItemDataRole.UserRole + 1


class FileList(QWidget):
    """Files chosen for a tool, with drag and drop and reordering."""

    changed = Signal()

    def __init__(self, extensions: tuple[str, ...], kinds_label: str, parent=None, max_files: int | None = None):
        super().__init__(parent)
        self.extensions = tuple(e.lower() for e in extensions)
        self.max_files = max_files
        self.passwords: dict[str, str] = {}
        self.info: dict[str, dict] = {}
        self._signals = _InfoSignals()
        self._signals.done.connect(self._on_info)
        self.setAcceptDrops(True)

        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setIconSize(QSize(28, 28))
        self.list.setSpacing(2)
        self.list.model().rowsMoved.connect(lambda *a: self.changed.emit())
        self.list.setAcceptDrops(True)

        self.drop = QLabel()
        self.drop.setObjectName("DropZone")
        self.drop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop.setWordWrap(True)
        self.drop.setText(f"<div style='font-size:15px;font-weight:600'>Drop {kinds_label.lower()} here</div>"
                          f"<div style='margin-top:6px'>or click <b>Add files</b></div>")
        self.drop.setMinimumHeight(180)

        self.stack = QStackedLayout()
        self.stack.addWidget(self.drop)
        self.stack.addWidget(self.list)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.stack)
        self._refresh()

    # -- public ---------------------------------------------------------------

    def paths(self) -> list[str]:
        return [self.list.item(i).data(ROLE_PATH) for i in range(self.list.count())]

    def add_paths(self, paths) -> list[str]:
        added, rejected = [], []
        existing = set(self.paths())
        for raw in paths:
            p = Path(raw)
            candidates = sorted(p.rglob("*")) if p.is_dir() else [p]
            for c in candidates:
                if not c.is_file():
                    continue
                if not str(c).lower().endswith(self.extensions):
                    if not p.is_dir():
                        rejected.append(c.name)
                    continue
                key = str(c)
                if key in existing:
                    continue
                if self.max_files and len(existing) >= self.max_files:
                    if self.max_files == 1:
                        self.clear()
                        existing = set()
                    else:
                        break
                existing.add(key)
                self._add_item(key)
                added.append(key)
        self._refresh()
        if added:
            self.changed.emit()
        self.rejected = rejected
        return added

    def remove_selected(self):
        for item in self.list.selectedItems():
            self.passwords.pop(item.data(ROLE_PATH), None)
            self.list.takeItem(self.list.row(item))
        self._refresh()
        self.changed.emit()

    def clear(self):
        self.list.clear()
        self.passwords.clear()
        self._refresh()
        self.changed.emit()

    def move_selected(self, delta: int):
        rows = sorted(self.list.row(i) for i in self.list.selectedItems())
        if not rows:
            return
        if delta > 0:
            rows.reverse()
        for row in rows:
            new = row + delta
            if 0 <= new < self.list.count():
                item = self.list.takeItem(row)
                self.list.insertItem(new, item)
                item.setSelected(True)
        self.changed.emit()

    def sort_by_name(self):
        paths = sorted(self.paths(), key=lambda s: Path(s).name.lower())
        self.list.clear()
        for p in paths:
            self._add_item(p, reload=False)
        self.changed.emit()

    def locked_files(self) -> list[str]:
        return [p for p in self.paths() if self.info.get(p, {}).get("locked") and p not in self.passwords]

    # -- internals ------------------------------------------------------------

    def _add_item(self, path: str, reload: bool = True):
        item = QListWidgetItem()
        item.setData(ROLE_PATH, path)
        item.setToolTip(path)
        self.list.addItem(item)
        if reload or path not in self.info:
            item.setText(f"{Path(path).name}\nReading…")
            item.setIcon(icons.icon("file", theme.current["muted"], 28))
            QThreadPool.globalInstance().start(_InfoTask(path, self._signals))
        else:
            self._decorate(item, self.info[path])

    def _on_info(self, path: str, info: dict):
        self.info[path] = info
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(ROLE_PATH) == path:
                self._decorate(item, info)
        self.changed.emit()

    def _decorate(self, item: QListWidgetItem, info: dict):
        path = item.data(ROLE_PATH)
        bits = []
        if "pages" in info:
            bits.append(f"{info['pages']} page{'s' if info['pages'] != 1 else ''}")
        if "dims" in info:
            bits.append(f"{info['dims'][0]} × {info['dims'][1]} px")
        bits.append(human_size(info.get("size", 0)))
        color = theme.current["muted"]
        name = "file"
        if info.get("locked"):
            bits.append("password needed" if path not in self.passwords else "password entered")
            name, color = "lock", theme.current["accent"]
        elif info.get("error"):
            bits.append(info["error"])
            name, color = "error", theme.current["danger"]
        elif path.lower().endswith(tb.EXTENSIONS[tb.IMAGE]):
            name = "image"
        item.setText(f"{Path(path).name}\n{' · '.join(bits)}")
        item.setIcon(icons.icon(name, color, 28))

    def refresh_item(self, path: str):
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(ROLE_PATH) == path:
                self._decorate(item, self.info.get(path, {}))

    def _refresh(self):
        self.stack.setCurrentIndex(1 if self.list.count() else 0)

    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop.setProperty("active", True)
            self.drop.style().polish(self.drop)

    def dragLeaveEvent(self, event):  # noqa: N802
        self.drop.setProperty("active", False)
        self.drop.style().polish(self.drop)

    def dropEvent(self, event):  # noqa: N802
        self.drop.setProperty("active", False)
        self.drop.style().polish(self.drop)
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.add_paths(paths)
            event.acceptProposedAction()


# ----------------------------------------------------------------------------
# Option form
# ----------------------------------------------------------------------------


class ColorButton(QPushButton):
    changed = Signal()

    def __init__(self, value="#000000"):
        super().__init__()
        self._value = value
        self.clicked.connect(self._pick)
        self._paint()

    def value(self):
        return self._value

    def set_value(self, value):
        self._value = value or "#000000"
        self._paint()

    def _paint(self):
        c = QColor(self._value)
        text = "#ffffff" if c.lightness() < 140 else "#000000"
        self.setText(self._value.upper())
        self.setStyleSheet(f"QPushButton {{ background: {self._value}; color: {text}; }}")

    def _pick(self):
        color = QColorDialog.getColor(QColor(self._value), self, "Choose a colour")
        if color.isValid():
            self.set_value(color.name())
            self.changed.emit()


class PasswordField(QWidget):
    changed = Signal()

    def __init__(self, confirm: bool):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setPlaceholderText("Password")
        self.show_btn = QToolButton()
        self.show_btn.setText("Show")
        self.show_btn.setCheckable(True)
        self.show_btn.toggled.connect(self._toggle)
        row.addWidget(self.edit)
        row.addWidget(self.show_btn)
        layout.addLayout(row)
        self.confirm = None
        if confirm:
            self.confirm = QLineEdit()
            self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
            self.confirm.setPlaceholderText("Type it again")
            layout.addWidget(self.confirm)
            self.confirm.textChanged.connect(self._check)
        self.edit.textChanged.connect(self._check)

    def _toggle(self, on):
        mode = QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        self.edit.setEchoMode(mode)
        if self.confirm:
            self.confirm.setEchoMode(mode)
        self.show_btn.setText("Hide" if on else "Show")

    def _check(self):
        if self.confirm is not None:
            bad = bool(self.confirm.text()) and self.confirm.text() != self.edit.text()
            self.confirm.setProperty("invalid", bad)
            self.confirm.style().polish(self.confirm)
        self.changed.emit()

    def value(self):
        return self.edit.text()

    def set_value(self, value):
        self.edit.setText(value or "")

    def problem(self) -> str | None:
        if self.confirm is not None and self.edit.text() and self.confirm.text() != self.edit.text():
            return "The two passwords do not match."
        return None


class ImagePicker(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Choose an image (PNG with transparency works best)")
        btn = QPushButton("Browse…")
        btn.clicked.connect(self._browse)
        layout.addWidget(self.edit)
        layout.addWidget(btn)
        self.edit.textChanged.connect(self.changed)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose an image", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if path:
            self.edit.setText(path)

    def value(self):
        return self.edit.text()

    def set_value(self, value):
        self.edit.setText(value or "")


class LanguagePicker(QListWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        from pdftoolbox.tools.ocr import language_choices

        self.setMaximumHeight(130)
        for code, name in language_choices():
            item = QListWidgetItem(name)
            item.setData(ROLE_PATH, code)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.addItem(item)
        if not self.count():
            item = QListWidgetItem("No OCR languages installed")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.addItem(item)
        self.itemChanged.connect(lambda *_: self.changed.emit())

    def value(self):
        codes = [self.item(i).data(ROLE_PATH) for i in range(self.count())
                 if self.item(i).checkState() == Qt.CheckState.Checked and self.item(i).data(ROLE_PATH)]
        return codes or ["eng"]

    def set_value(self, value):
        wanted = set(value or ["eng"])
        self.blockSignals(True)
        for i in range(self.count()):
            code = self.item(i).data(ROLE_PATH)
            if code:
                self.item(i).setCheckState(Qt.CheckState.Checked if code in wanted else Qt.CheckState.Unchecked)
        self.blockSignals(False)


class FontPicker(QComboBox):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.addItem("Default", "")
        for family in QFontDatabase.families():
            if not QFontDatabase.isPrivateFamily(family):
                self.addItem(family, family)
        self.setMaxVisibleItems(20)
        self.currentIndexChanged.connect(lambda *_: self.changed.emit())

    def value(self):
        return self.currentData() or ""

    def set_value(self, value):
        index = self.findData(value or "")
        self.setCurrentIndex(max(0, index))


class OptionsForm(QWidget):
    """Builds input widgets from a tool's option list."""

    changed = Signal()

    def __init__(self, options: list[tb.Option], parent=None, special=None):
        super().__init__(parent)
        self.options = options
        self.widgets: dict[str, QWidget] = {}
        self.rows: dict[str, int] = {}
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setHorizontalSpacing(14)
        self.form.setVerticalSpacing(10)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        special = special or {}
        # Large widgets (page organiser) are placed by the page, outside the form.
        self.external: dict[str, QWidget] = {}
        for opt in options:
            widget = special.get(type(opt), self._make)(opt)
            self.widgets[opt.key] = widget
            if isinstance(opt, tb.PageOrganizer):
                self.external[opt.key] = widget
                continue
            if isinstance(opt, tb.Flag) or isinstance(opt, (tb.PageOrganizer, tb.Pipeline)):
                row_label = None
            else:
                row_label = QLabel(opt.label)
            if opt.help:
                widget.setToolTip(opt.help)
            container = widget
            if opt.help and not isinstance(opt, tb.Flag):
                container = QWidget()
                v = QVBoxLayout(container)
                v.setContentsMargins(0, 0, 0, 0)
                v.setSpacing(3)
                v.addWidget(widget)
                hint = QLabel(opt.help)
                hint.setObjectName("Muted")
                hint.setWordWrap(True)
                v.addWidget(hint)
            if row_label is None:
                self.form.addRow(container)
            else:
                self.form.addRow(row_label, container)
            self.rows[opt.key] = self.form.rowCount() - 1
        self.set_values({o.key: o.default for o in options})
        self._update_visibility()

    def _emit(self, *_):
        self._update_visibility()
        self.changed.emit()

    def _make(self, opt: tb.Option) -> QWidget:
        if isinstance(opt, tb.Choice):
            w = QComboBox()
            for value, label in opt.choices:
                w.addItem(label, value)
            w.currentIndexChanged.connect(self._emit)
        elif isinstance(opt, tb.Integer):
            w = QSpinBox()
            w.setRange(opt.minimum, opt.maximum)
            w.setSuffix(opt.suffix)
            w.valueChanged.connect(self._emit)
        elif isinstance(opt, tb.Number):
            w = QDoubleSpinBox()
            w.setRange(opt.minimum, opt.maximum)
            w.setDecimals(opt.decimals)
            w.setSuffix(opt.suffix)
            w.valueChanged.connect(self._emit)
        elif isinstance(opt, tb.Flag):
            w = QCheckBox(opt.label)
            w.toggled.connect(self._emit)
        elif isinstance(opt, tb.Password):
            w = PasswordField(opt.confirm)
            w.changed.connect(self._emit)
        elif isinstance(opt, tb.Color):
            w = ColorButton()
            w.changed.connect(self._emit)
        elif isinstance(opt, tb.Font):
            w = FontPicker()
            w.changed.connect(self._emit)
        elif isinstance(opt, tb.ImageFile):
            w = ImagePicker()
            w.changed.connect(self._emit)
        elif isinstance(opt, tb.Languages):
            w = LanguagePicker()
            w.changed.connect(self._emit)
        elif isinstance(opt, (tb.Text, tb.Pages)):
            if isinstance(opt, tb.Text) and opt.multiline:
                w = QPlainTextEdit()
                w.setMaximumHeight(90)
                w.textChanged.connect(self._emit)
            else:
                w = QLineEdit()
                w.setPlaceholderText(opt.placeholder)
                w.textChanged.connect(self._emit)
        else:
            w = QLabel("(unsupported option)")
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        return w

    def value_of(self, opt: tb.Option):
        w = self.widgets[opt.key]
        if hasattr(w, "value") and callable(w.value) and not isinstance(w, (QSpinBox, QDoubleSpinBox)):
            return w.value()
        if isinstance(w, QComboBox):
            return w.currentData()
        if isinstance(w, (QSpinBox, QDoubleSpinBox)):
            return w.value()
        if isinstance(w, QCheckBox):
            return w.isChecked()
        if isinstance(w, QPlainTextEdit):
            return w.toPlainText()
        if isinstance(w, QLineEdit):
            return w.text()
        return None

    def values(self) -> dict[str, Any]:
        return {opt.key: self.value_of(opt) for opt in self.options}

    def set_values(self, values: dict[str, Any]):
        for opt in self.options:
            if opt.key not in values:
                continue
            value = values[opt.key]
            w = self.widgets[opt.key]
            w.blockSignals(True)
            try:
                if hasattr(w, "set_value"):
                    w.set_value(value)
                elif isinstance(w, QComboBox):
                    index = w.findData(value)
                    if index < 0 and value is not None:
                        index = next((i for i in range(w.count()) if str(w.itemData(i)) == str(value)), -1)
                    w.setCurrentIndex(max(0, index))
                elif isinstance(w, QSpinBox):
                    w.setValue(int(value or 0))
                elif isinstance(w, QDoubleSpinBox):
                    w.setValue(float(value or 0))
                elif isinstance(w, QCheckBox):
                    w.setChecked(bool(value))
                elif isinstance(w, QPlainTextEdit):
                    w.setPlainText(value or "")
                elif isinstance(w, QLineEdit):
                    w.setText("" if value is None else str(value))
            finally:
                w.blockSignals(False)
        self._update_visibility()

    def _update_visibility(self):
        values = self.values()
        for opt in self.options:
            if opt.key in self.external:
                self.external[opt.key].setVisible(opt.is_visible(values))
            else:
                self.form.setRowVisible(self.rows[opt.key], opt.is_visible(values))

    def problems(self) -> list[str]:
        out = []
        for opt in self.options:
            w = self.widgets[opt.key]
            if opt.is_visible(self.values()) and hasattr(w, "problem"):
                p = w.problem()
                if p:
                    out.append(p)
        return out
