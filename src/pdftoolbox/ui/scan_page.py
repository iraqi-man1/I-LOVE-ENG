"""Scan to PDF: find a scanner, scan pages, arrange them and save one PDF."""

from __future__ import annotations

import datetime as dt
import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImageReader, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListView, QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton, QSplitter, QVBoxLayout,
    QWidget,
)

from pdftoolbox.core.context import JobSpec, safe_name, unique_path
from pdftoolbox.scan import ScanError, ScannerInfo, ScanSettings, get_backend
from pdftoolbox.scan.base import BW, COLOR, DUPLEX, FEEDER, FLATBED, GRAY

from . import desktop, icons, settings, theme
from .background import Worker
from .job_runner import JobRunner

ROLE_PATH = Qt.ItemDataRole.UserRole
ROLE_ROTATE = Qt.ItemDataRole.UserRole + 1
SOURCE_LABELS = {FLATBED: "Flatbed (glass)", FEEDER: "Document feeder", DUPLEX: "Document feeder, both sides"}


class DeviceFinder(Worker):
    found = Signal(list)
    error = Signal(str)

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend

    def run(self):
        try:
            self.found.emit(self.backend.list_devices())
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


class ScanWorker(Worker):
    page = Signal(str)
    error = Signal(str)
    done = Signal(int)

    def __init__(self, backend, device, scan_settings, folder, parent=None):
        super().__init__(parent)
        self.backend, self.device, self.settings, self.folder = backend, device, scan_settings, folder
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            count = self.backend.scan(self.device, self.settings, Path(self.folder), lambda p: self.page.emit(str(p)),
                                      lambda: self._cancel)
            self.done.emit(count)
        except ScanError as exc:
            self.error.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Scanning failed: {exc}")


def load_thumb(path: str, size: int, rotate: int = 0) -> QPixmap:
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    original = reader.size()
    if original.isValid():
        reader.setScaledSize(original.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    pm = QPixmap.fromImage(image)
    if rotate:
        pm = pm.transformed(QTransform().rotate(rotate), Qt.TransformationMode.SmoothTransformation)
    framed = QPixmap(pm.size())
    framed.fill(Qt.GlobalColor.white)
    painter = QPainter(framed)
    painter.drawPixmap(0, 0, pm)
    painter.setPen(QColor(theme.current["border"]))
    painter.drawRect(0, 0, pm.width() - 1, pm.height() - 1)
    painter.end()
    return framed


class ScanPage(QWidget):
    back = Signal()
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.backend = get_backend()
        self.devices: list[ScannerInfo] = []
        self.finder = None
        self.worker = None
        self.workdir = Path(tempfile.mkdtemp(prefix="pdftoolbox-scan-"))
        self.runner = JobRunner(self)
        self.runner.progress.connect(lambda f, m: (self.save_progress.setValue(int(f * 1000)), self._say(m)))
        self.runner.finished.connect(self._saved)
        self.runner.failed.connect(lambda m: self._save_done(error=m.partition("\n\n")[0]))
        self.runner.cancelled.connect(lambda: self._save_done(error="Saving was cancelled."))

        back = QPushButton("  All tools")
        back.setIcon(icons.icon("back", theme.current["text"], 16))
        back.setObjectName("Link")
        back.clicked.connect(self.back)
        badge = QLabel()
        badge.setPixmap(icons.badge("scan", icons.CATEGORY_COLORS["Scan"], 48))
        title = QLabel("Scan to PDF")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Scan pages from your scanner or printer, arrange them, and save them as one PDF.")
        subtitle.setObjectName("PageSubtitle")
        head = QHBoxLayout()
        head.setSpacing(14)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(title)
        texts.addWidget(subtitle)
        head.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        head.addLayout(texts, 1)

        # Scanner settings
        side = QFrame()
        side.setObjectName("Panel")
        side.setMinimumWidth(290)
        side.setMaximumWidth(360)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(16, 16, 16, 16)
        heading = QLabel("Scanner")
        heading.setObjectName("SectionTitle")
        sl.addWidget(heading)
        device_row = QHBoxLayout()
        self.device_box = QComboBox()
        self.device_box.currentIndexChanged.connect(self._device_changed)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.find_devices)
        device_row.addWidget(self.device_box, 1)
        device_row.addWidget(refresh)
        sl.addLayout(device_row)
        self.device_status = QLabel("")
        self.device_status.setObjectName("Muted")
        self.device_status.setWordWrap(True)
        sl.addWidget(self.device_status)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.source_box = QComboBox()
        self.color_box = QComboBox()
        for value, label in ((COLOR, "Colour"), (GRAY, "Grayscale"), (BW, "Black and white (text)")):
            self.color_box.addItem(label, value)
        self.dpi_box = QComboBox()
        for dpi, label in ((150, "150 dpi (fast)"), (200, "200 dpi (recommended)"), (300, "300 dpi (best for OCR)"),
                           (600, "600 dpi (photos, slow)")):
            self.dpi_box.addItem(label, dpi)
        self.size_box = QComboBox()
        for value, label in (("a4", "A4"), ("letter", "Letter"), ("legal", "Legal"), ("a5", "A5"),
                             ("max", "Whole scanner glass")):
            self.size_box.addItem(label, value)
        form.addRow("Source", self.source_box)
        form.addRow("Colour", self.color_box)
        form.addRow("Resolution", self.dpi_box)
        form.addRow("Page size", self.size_box)
        sl.addLayout(form)
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.setObjectName("Primary")
        self.scan_btn.setIcon(icons.icon("scan", "#ffffff", 18))
        self.scan_btn.clicked.connect(self.scan)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.hide()
        sl.addSpacing(6)
        sl.addWidget(self.scan_btn)
        sl.addWidget(self.stop_btn)
        self.scan_status = QLabel("")
        self.scan_status.setWordWrap(True)
        self.scan_status.setObjectName("Muted")
        sl.addWidget(self.scan_status)
        sl.addStretch(1)
        imp = QPushButton("Add images from files…")
        imp.setIcon(icons.icon("image", theme.current["text"], 16))
        imp.clicked.connect(self._import)
        sl.addWidget(imp)
        tip = QLabel("Tip: put the next page on the glass and press Scan again. Each scan is added to the list.")
        tip.setWordWrap(True)
        tip.setObjectName("Muted")
        sl.addWidget(tip)
        self._restore()

        # Pages
        pages_box = QFrame()
        pages_box.setObjectName("Panel")
        pl = QVBoxLayout(pages_box)
        pl.setContentsMargins(14, 14, 14, 14)
        bar = QHBoxLayout()
        self.pages_label = QLabel("<b>Pages</b>")
        bar.addWidget(self.pages_label)
        bar.addStretch(1)
        for icon_name, tip_text, slot in (("rotate_left", "Rotate left", lambda: self._rotate(-90)),
                                          ("rotate", "Rotate right", lambda: self._rotate(90)),
                                          ("trash", "Remove selected pages", self._delete)):
            b = QPushButton("")
            b.setIcon(icons.icon(icon_name, theme.current["text"], 16))
            b.setToolTip(tip_text)
            b.clicked.connect(slot)
            bar.addWidget(b)
        clear = QPushButton("Remove all")
        clear.clicked.connect(self._clear)
        bar.addWidget(clear)
        pl.addLayout(bar)
        self.grid = QListWidget()
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setMovement(QListView.Movement.Snap)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.grid.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.grid.setIconSize(QSize(150, 150))
        self.grid.setGridSize(QSize(176, 190))
        self.grid.setSpacing(8)
        self.grid.currentItemChanged.connect(self._preview)
        self.grid.model().rowsMoved.connect(lambda *a: self._renumber())
        self.empty = QLabel("Scanned pages will appear here.\nDrag them to change the order.")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setObjectName("Muted")
        pl.addWidget(self.grid, 1)
        pl.addWidget(self.empty)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumWidth(220)
        self.preview.setObjectName("Panel")

        split = QSplitter()
        split.addWidget(side)
        split.addWidget(pages_box)
        split.addWidget(self.preview)
        split.setChildrenCollapsible(False)
        split.setSizes([300, 640, 300])

        # Save bar
        save_box = QFrame()
        save_box.setObjectName("Panel")
        sv = QVBoxLayout(save_box)
        sv.setContentsMargins(16, 12, 16, 12)
        row = QHBoxLayout()
        row.addWidget(QLabel("<b>File name</b>"))
        self.name_edit = QLineEdit(self._default_name())
        self.name_edit.setMinimumWidth(240)
        row.addWidget(self.name_edit, 1)
        row.addWidget(QLabel(".pdf  in"))
        self.folder = settings.get("scan/folder", str(Path.home() / "Documents"))
        self.folder_label = QLabel(self.folder)
        self.folder_label.setObjectName("Muted")
        row.addWidget(self.folder_label)
        change = QPushButton("Change…")
        change.clicked.connect(self._choose_folder)
        row.addWidget(change)
        sv.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Quality"))
        self.quality_box = QComboBox()
        for value, label in (("small", "Small file"), ("balanced", "Balanced"), ("high", "High"),
                             ("lossless", "Lossless (large)")):
            self.quality_box.addItem(label, value)
        self.quality_box.setCurrentIndex(max(0, self.quality_box.findData(settings.get("scan/quality", "balanced"))))
        row2.addWidget(self.quality_box)
        self.ocr_box = QCheckBox("Make text searchable (OCR)")
        self.ocr_box.setChecked(bool(settings.get("scan/ocr", False)))
        self.lang_box = QComboBox()
        from pdftoolbox.tools.ocr import check as ocr_check, language_choices

        languages = language_choices()
        codes = {code for code, _ in languages}
        if {"eng", "ara"} <= codes:
            self.lang_box.addItem("English + Arabic", ["eng", "ara"])
        for code, name in languages:
            self.lang_box.addItem(name, [code])
        saved_lang = settings.get("scan/languages")
        if saved_lang:
            self.lang_box.setCurrentIndex(max(0, self.lang_box.findData(saved_lang)))
        self.ocr_problem = ocr_check()
        if self.ocr_problem:
            self.ocr_box.setEnabled(False)
            self.ocr_box.setToolTip(self.ocr_problem)
            self.ocr_box.setChecked(False)
        self.lang_box.setEnabled(self.ocr_box.isChecked())
        self.ocr_box.toggled.connect(self.lang_box.setEnabled)
        row2.addSpacing(16)
        row2.addWidget(self.ocr_box)
        row2.addWidget(self.lang_box)
        row2.addStretch(1)
        self.save_progress = QProgressBar()
        self.save_progress.setRange(0, 1000)
        self.save_progress.setTextVisible(False)
        self.save_progress.setMaximumWidth(200)
        self.save_progress.hide()
        self.save_status = QLabel("")
        self.save_status.setObjectName("Muted")
        self.open_btn = QPushButton("Open")
        self.open_btn.clicked.connect(lambda: self.last_saved and desktop.open_path(self.last_saved))
        self.open_btn.hide()
        self.reveal_btn = QPushButton("Show in folder")
        self.reveal_btn.clicked.connect(lambda: self.last_saved and desktop.reveal(self.last_saved))
        self.reveal_btn.hide()
        self.save_btn = QPushButton("Save PDF")
        self.save_btn.setObjectName("Primary")
        self.save_btn.clicked.connect(self.save)
        row2.addWidget(self.save_status)
        row2.addWidget(self.save_progress)
        row2.addWidget(self.open_btn)
        row2.addWidget(self.reveal_btn)
        row2.addWidget(self.save_btn)
        sv.addLayout(row2)
        self.last_saved = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 16, 28, 20)
        layout.setSpacing(12)
        layout.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(head)
        layout.addWidget(split, 1)
        layout.addWidget(save_box)
        self._renumber()

    # -- devices -------------------------------------------------------------

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if not self.devices and self.finder is None:
            self.find_devices()

    def find_devices(self):
        reason = self.backend.unavailable_reason()
        if reason:
            self.device_status.setText(reason)
            self.scan_btn.setEnabled(False)
            return
        if self.finder is not None:
            return
        self.device_status.setText("Looking for scanners…")
        self.device_box.clear()
        self.scan_btn.setEnabled(False)
        self.finder = DeviceFinder(self.backend, self)
        self.finder.found.connect(self._devices_found)
        self.finder.error.connect(lambda m: self._devices_found([], m))
        self.finder.finished.connect(self._finder_done)
        self.finder.start()

    def _finder_done(self):
        self.finder = None

    def _devices_found(self, devices, error=None):
        self.devices = devices
        self.device_box.clear()
        for d in devices:
            self.device_box.addItem(icons.icon("scan", theme.current["text"], 16), d.name, d.id)
        if devices:
            last = settings.get("scan/device")
            index = self.device_box.findData(last)
            self.device_box.setCurrentIndex(max(0, index))
            self.device_status.setText(f"{len(devices)} scanner{'s' if len(devices) != 1 else ''} found.")
            self.scan_btn.setEnabled(True)
        else:
            self.device_status.setText(error or "No scanner found. Check that it is switched on, connected and its "
                                                "driver is installed, then click Refresh. You can also add images "
                                                "from files.")
            self.scan_btn.setEnabled(False)

    def _device_changed(self):
        device = self._device()
        self.source_box.clear()
        if device:
            for source in device.sources:
                self.source_box.addItem(SOURCE_LABELS[source], source)
            index = self.source_box.findData(settings.get("scan/source", FLATBED))
            self.source_box.setCurrentIndex(max(0, index))

    def _device(self):
        dev_id = self.device_box.currentData()
        return next((d for d in self.devices if d.id == dev_id), None)

    def _restore(self):
        for box, key, default in ((self.color_box, "scan/color", COLOR), (self.dpi_box, "scan/dpi", 200),
                                  (self.size_box, "scan/page", "a4")):
            box.setCurrentIndex(max(0, box.findData(settings.get(key, default))))

    # -- scanning ------------------------------------------------------------

    def scan(self):
        device = self._device()
        if device is None or self.worker is not None:
            return
        scan_settings = ScanSettings(source=self.source_box.currentData() or FLATBED,
                                     color=self.color_box.currentData(), dpi=int(self.dpi_box.currentData()),
                                     page=self.size_box.currentData())
        for key, value in (("scan/device", device.id), ("scan/source", scan_settings.source),
                           ("scan/color", scan_settings.color), ("scan/dpi", scan_settings.dpi),
                           ("scan/page", scan_settings.page)):
            settings.put(key, value)
        self.worker = ScanWorker(self.backend, device, scan_settings, self.workdir, self)
        self.worker.page.connect(self._add_page)
        self.worker.error.connect(self._scan_error)
        self.worker.done.connect(lambda n: self.scan_status.setText(
            f"Scanned {n} page{'s' if n != 1 else ''}." if n else "Nothing was scanned."))
        self.worker.finished.connect(self._scan_finished)
        self.scan_btn.setEnabled(False)
        self.stop_btn.show()
        self.scan_status.setObjectName("Muted")
        self.scan_status.style().polish(self.scan_status)
        self.scan_status.setText("Scanning…")
        self.busy_changed.emit(True)
        self.worker.start()

    def _stop(self):
        if self.worker:
            self.worker.cancel()
            self.scan_status.setText("Stopping after the current page…")

    def _scan_error(self, message):
        self.scan_status.setObjectName("Error")
        self.scan_status.style().polish(self.scan_status)
        self.scan_status.setText(message)

    def _scan_finished(self):
        self.worker = None
        self.stop_btn.hide()
        self.scan_btn.setEnabled(self._device() is not None)
        self.busy_changed.emit(False)

    def _add_page(self, path):
        item = QListWidgetItem(QIcon(load_thumb(path, 150)), "")
        item.setData(ROLE_PATH, path)
        item.setData(ROLE_ROTATE, 0)
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.grid.addItem(item)
        self.grid.clearSelection()
        self.grid.setCurrentItem(item)
        self.grid.scrollToItem(item)
        self._renumber()

    def _import(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add images", settings.get("ui/last_dir", str(Path.home())),
                                                "Images (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp)")
        for p in paths:
            target = unique_path(self.workdir / Path(p).name)
            shutil.copyfile(p, target)
            self._add_page(str(target))

    # -- arranging -----------------------------------------------------------

    def _renumber(self):
        n = self.grid.count()
        for i in range(n):
            self.grid.item(i).setText(f"Page {i + 1}")
        self.pages_label.setText(f"<b>Pages</b> ({n})" if n else "<b>Pages</b>")
        self.empty.setVisible(n == 0)
        self.save_btn.setEnabled(n > 0 and not self.runner.running)
        if n == 0:
            self.preview.clear()

    def _rotate(self, degrees):
        for item in self.grid.selectedItems():
            angle = (item.data(ROLE_ROTATE) + degrees) % 360
            item.setData(ROLE_ROTATE, angle)
            item.setIcon(QIcon(load_thumb(item.data(ROLE_PATH), 150, angle)))
        self._preview(self.grid.currentItem())

    def _delete(self):
        for item in self.grid.selectedItems():
            self.grid.takeItem(self.grid.row(item))
        self._renumber()

    def _clear(self):
        if self.grid.count() and QMessageBox.question(self, "Remove all pages", "Remove every scanned page?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.grid.clear()
        self._renumber()

    def _preview(self, item, *_):
        if item is None:
            self.preview.clear()
            return
        size = max(200, min(self.preview.width(), self.preview.height()) - 24)
        framed = load_thumb(item.data(ROLE_PATH), size, item.data(ROLE_ROTATE))
        self.preview.setPixmap(framed)

    # -- saving --------------------------------------------------------------

    def _default_name(self):
        return "Scan " + dt.datetime.now().strftime("%Y-%m-%d %H.%M")

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Save scans to", self.folder)
        if folder:
            self.folder = folder
            self.folder_label.setText(folder)
            settings.put("scan/folder", folder)

    def _say(self, message):
        if message:
            self.save_status.setText(message)

    def save(self):
        if not self.grid.count() or self.runner.running:
            return
        paths, rotations = [], {}
        for i in range(self.grid.count()):
            item = self.grid.item(i)
            paths.append(item.data(ROLE_PATH))
            if item.data(ROLE_ROTATE):
                rotations[item.data(ROLE_PATH)] = item.data(ROLE_ROTATE)
        name = safe_name(self.name_edit.text().strip() or self._default_name())
        if name.lower().endswith(".pdf"):
            name = name[:-4]
        Path(self.folder).mkdir(parents=True, exist_ok=True)
        target = unique_path(Path(self.folder) / f"{name}.pdf")
        ocr = self.ocr_box.isChecked() and self.ocr_box.isEnabled()
        settings.put("scan/quality", self.quality_box.currentData())
        settings.put("scan/ocr", ocr)
        settings.put("scan/languages", self.lang_box.currentData())
        options = {"rotations": rotations, "quality": self.quality_box.currentData(), "ocr": ocr,
                   "languages": self.lang_box.currentData() or ["eng"]}
        spec = JobSpec("scan_save", paths, options, output_file=str(target))
        self.save_btn.setEnabled(False)
        self.save_progress.setValue(0)
        self.save_progress.show()
        self.open_btn.hide()
        self.reveal_btn.hide()
        self.save_status.setObjectName("Muted")
        self.save_status.style().polish(self.save_status)
        self.save_status.setText("Saving…")
        self.busy_changed.emit(True)
        self.runner.start(spec)

    def _saved(self, results):
        result = results[0] if results else None
        if result is None or result.error:
            self._save_done(error=result.error if result else "Saving failed.")
            return
        self.last_saved = result.outputs[0]
        self._save_done()
        self.save_status.setObjectName("Success")
        self.save_status.style().polish(self.save_status)
        self.save_status.setText(f"Saved {Path(self.last_saved).name}")
        self.open_btn.show()
        self.reveal_btn.show()
        self.name_edit.setText(self._default_name())
        if settings.open_when_done():
            desktop.open_path(self.last_saved)

    def _save_done(self, error=None):
        self.save_progress.hide()
        self.save_btn.setEnabled(self.grid.count() > 0)
        self.busy_changed.emit(False)
        if error:
            self.save_status.setObjectName("Error")
            self.save_status.style().polish(self.save_status)
            self.save_status.setText(error)

    def cleanup(self):
        shutil.rmtree(self.workdir, ignore_errors=True)
