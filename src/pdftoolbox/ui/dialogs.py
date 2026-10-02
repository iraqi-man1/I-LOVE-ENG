"""Settings, About and Update dialogs, plus the background update check."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QTextBrowser, QVBoxLayout,
)

from pdftoolbox import APP_NAME, GITHUB_REPO, __version__
from pdftoolbox.core.paths import find_libreoffice, find_tesseract, resources_dir, user_tessdata_dir
from pdftoolbox.updater import github
from pdftoolbox.updater.install import install

from . import icons, settings, theme


class UpdateCheck(QThread):
    found = Signal(object)
    none = Signal()
    error = Signal(str)

    def run(self):
        try:
            release = github.check_latest()
        except github.UpdateError as exc:
            self.error.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
            return
        if release:
            self.found.emit(release)
        else:
            self.none.emit()


class Download(QThread):
    progress = Signal(int, int)
    done = Signal(str)
    error = Signal(str)

    def __init__(self, release):
        super().__init__()
        self.release = release
        self.cancelled = False

    def run(self):
        try:
            folder = Path(tempfile.gettempdir()) / "pdftoolbox-updates"
            path = github.download(self.release, folder, lambda a, b: self.progress.emit(a, b),
                                   lambda: self.cancelled)
            self.done.emit(str(path))
        except github.UpdateError as exc:
            self.error.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


class UpdateDialog(QDialog):
    def __init__(self, release, parent=None):
        super().__init__(parent)
        self.release = release
        self.download = None
        self.path = None
        self.setWindowTitle("Update available")
        self.setMinimumWidth(520)
        title = QLabel(f"<h3>{APP_NAME} {release.version} is available</h3>"
                       f"<p>You have version {__version__}.</p>")
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(release.notes or "No release notes.")
        notes.setMinimumHeight(180)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.hide()
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        self.install_btn = QPushButton("Download and install")
        self.install_btn.setObjectName("Primary")
        self.install_btn.clicked.connect(self._go)
        skip = QPushButton("Skip this version")
        skip.clicked.connect(self._skip)
        later = QPushButton("Later")
        later.clicked.connect(self.reject)
        page = QPushButton("Release page")
        page.setObjectName("Link")
        page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(release.page_url)))
        buttons = QHBoxLayout()
        buttons.addWidget(page)
        buttons.addStretch(1)
        buttons.addWidget(skip)
        buttons.addWidget(later)
        buttons.addWidget(self.install_btn)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(QLabel("<b>What's new</b>"))
        layout.addWidget(notes, 1)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addLayout(buttons)
        if not release.asset_url:
            self.install_btn.setEnabled(False)
            self.status.setText("This release has no installer for your computer yet. Open the release page for "
                                "details.")

    def _skip(self):
        settings.put("updates/skipped", self.release.version)
        self.reject()

    def _go(self):
        if self.path:
            self._install()
            return
        self.install_btn.setEnabled(False)
        self.progress.show()
        self.status.setText("Downloading…")
        self.download = Download(self.release)
        self.download.progress.connect(self._progress)
        self.download.done.connect(self._downloaded)
        self.download.error.connect(self._failed)
        self.download.start()

    def _progress(self, received, total):
        if total:
            self.progress.setValue(int(received * 1000 / total))
            self.status.setText(f"Downloading… {received / 1048576:.1f} of {total / 1048576:.1f} MB")

    def _downloaded(self, path):
        self.path = Path(path)
        self.progress.setValue(1000)
        self.status.setText("Download complete and verified.")
        self.install_btn.setText("Install and restart")
        self.install_btn.setEnabled(True)

    def _failed(self, message):
        self.progress.hide()
        self.status.setText(message)
        self.install_btn.setEnabled(True)

    def _install(self):
        busy = getattr(self.parent(), "is_busy", lambda: False)()
        if busy and QMessageBox.question(self, "Install update", "A task is still running. Stop it and install the "
                                         "update now?") != QMessageBox.StandardButton.Yes:
            return
        try:
            quit_now = install(self.path)
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"The update could not be installed: {exc}")
            return
        if quit_now:
            QApplication.instance().quit()
        else:
            self.status.setText("The installer has been opened. Drag the new version into your Applications folder, "
                                "then restart the app.")

    def reject(self):
        if self.download is not None and self.download.isRunning():
            self.download.cancelled = True
            self.download.wait(3000)
        super().reject()


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        self.same = QRadioButton("Next to the original file")
        self.folder = QRadioButton(f"In {settings.output_folder()}")
        (self.folder if settings.output_mode() == "folder" else self.same).setChecked(True)
        out = QVBoxLayout()
        out.addWidget(self.same)
        out.addWidget(self.folder)
        form.addRow("Save results", out)
        self.open_done = QCheckBox("Open the result when a task finishes")
        self.open_done.setChecked(settings.open_when_done())
        form.addRow("", self.open_done)
        self.theme_box = QComboBox()
        for value, label in (("system", "Same as system"), ("light", "Light"), ("dark", "Dark")):
            self.theme_box.addItem(label, value)
        self.theme_box.setCurrentIndex(max(0, self.theme_box.findData(settings.theme())))
        form.addRow("Appearance", self.theme_box)
        self.auto = QCheckBox("Check for updates automatically when online")
        self.auto.setChecked(settings.auto_update())
        form.addRow("Updates", self.auto)
        tess = find_tesseract()
        office = find_libreoffice()
        lang_btn = QPushButton("Open OCR languages folder")
        lang_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(user_tessdata_dir()))))
        lang_note = QLabel("To add an OCR language, download its .traineddata file from "
                           "<a href='https://github.com/tesseract-ocr/tessdata'>tesseract-ocr/tessdata</a> "
                           "and copy it, together with eng.traineddata, into this folder.")
        lang_note.setOpenExternalLinks(True)
        lang_note.setWordWrap(True)
        lang_note.setObjectName("Muted")
        form.addRow("OCR engine", QLabel("Installed" if tess else "Not found"))
        form.addRow("", lang_btn)
        form.addRow("", lang_note)
        form.addRow("LibreOffice", QLabel(str(office) if office else "Not found (needed for Office files on macOS)"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _save(self):
        settings.put("output/mode", "folder" if self.folder.isChecked() else "same")
        settings.put("output/open_when_done", self.open_done.isChecked())
        settings.put("updates/auto", self.auto.isChecked())
        changed = settings.theme() != self.theme_box.currentData()
        settings.put("ui/theme", self.theme_box.currentData())
        if changed:
            theme.apply(QApplication.instance(), self.theme_box.currentData())
            QMessageBox.information(self, "Appearance", "Restart the app to finish changing the appearance.")
        self.accept()


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setMinimumSize(560, 480)
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(72, 72))
        text = QLabel(f"<h2>{APP_NAME}</h2><p>Version {__version__}</p>"
                      "<p>Works completely offline. Your files never leave this computer.</p>"
                      f"<p><a href='https://github.com/{GITHUB_REPO}'>github.com/{GITHUB_REPO}</a></p>")
        text.setOpenExternalLinks(True)
        top = QHBoxLayout()
        top.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)
        top.addWidget(text, 1)
        notices = QPlainTextEdit()
        notices.setReadOnly(True)
        path = resources_dir() / "THIRD_PARTY_NOTICES.txt"
        notices.setPlainText(path.read_text(encoding="utf-8") if path.exists() else "See THIRD_PARTY_NOTICES.md.")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(QLabel("<b>Open-source components</b>"))
        layout.addWidget(notices, 1)
        layout.addWidget(buttons)
