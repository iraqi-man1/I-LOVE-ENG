"""The screen for one tool: files on the left, settings on the right."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QScrollArea,
    QSizePolicy, QSplitter, QToolButton, QVBoxLayout, QWidget,
)

from pdftoolbox.core.context import JobSpec, unique_path, safe_name
from pdftoolbox.tools import base as tb

from . import desktop, icons, settings, theme
from .job_runner import JobRunner
from .organizer import PageOrganizerWidget
from .pipeline import PipelineEditor
from .widgets import FileList, OptionsForm


def panel() -> QFrame:
    frame = QFrame()
    frame.setObjectName("Panel")
    return frame


def tool_button(icon_name: str, tip: str, slot) -> QToolButton:
    b = QToolButton()
    b.setIcon(icons.icon(icon_name, theme.current["text"], 18))
    b.setToolTip(tip)
    b.clicked.connect(slot)
    return b


class ToolPage(QWidget):
    back = Signal()
    busy_changed = Signal(bool)

    def __init__(self, tool: tb.Tool, parent=None):
        super().__init__(parent)
        self.tool = tool
        self.setObjectName("Page")
        self.runner = JobRunner(self)
        self.runner.progress.connect(self._on_progress)
        self.runner.finished.connect(self._on_finished)
        self.runner.failed.connect(self._on_failed)
        self.runner.cancelled.connect(self._on_cancelled)
        self.started_at = 0.0
        self.organizer = None
        self.pipeline = None

        # Header
        back = QPushButton("  All tools")
        back.setIcon(icons.icon("back", theme.current["text"], 16))
        back.setObjectName("Link")
        back.clicked.connect(self.back)
        badge = QLabel()
        badge.setPixmap(icons.badge(tool.icon, icons.CATEGORY_COLORS.get(tool.category, theme.ACCENT), 48))
        title = QLabel(tool.name)
        title.setObjectName("PageTitle")
        subtitle = QLabel(tool.description)
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        head_text = QVBoxLayout()
        head_text.setSpacing(2)
        head_text.addWidget(title)
        head_text.addWidget(subtitle)
        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        header.addLayout(head_text, 1)

        self.warning = QLabel()
        self.warning.setObjectName("Banner")
        self.warning.setWordWrap(True)
        self.warning.setContentsMargins(12, 10, 12, 10)
        self.warning.setOpenExternalLinks(True)
        self.warning.hide()

        # Files
        label = tb.KIND_LABELS[tool.inputs[0]] if len(tool.inputs) == 1 else "files"
        has_organizer = any(isinstance(o, tb.PageOrganizer) for o in tool.options)
        self.files = FileList(tool.extensions, label, max_files=tool.max_files)
        self.files.changed.connect(self._files_changed)
        files_box = panel()
        fl = QVBoxLayout(files_box)
        fl.setContentsMargins(14, 14, 14, 14)
        bar = QHBoxLayout()
        add = QPushButton("Add files")
        add.setIcon(icons.icon("add", theme.current["text"], 16))
        add.clicked.connect(self._browse)
        bar.addWidget(add)
        if tool.max_files != 1:
            folder = QPushButton("Add folder")
            folder.setIcon(icons.icon("folder", theme.current["text"], 16))
            folder.clicked.connect(self._browse_folder)
            bar.addWidget(folder)
        bar.addStretch(1)
        bar.addWidget(tool_button("up", "Move up", lambda: self.files.move_selected(-1)))
        bar.addWidget(tool_button("down", "Move down", lambda: self.files.move_selected(1)))
        sort = QPushButton("A–Z")
        sort.setToolTip("Sort by name")
        sort.clicked.connect(self.files.sort_by_name)
        bar.addWidget(sort)
        bar.addWidget(tool_button("trash", "Remove selected", self.files.remove_selected))
        clear = QPushButton("Clear")
        clear.clicked.connect(self.files.clear)
        bar.addWidget(clear)
        fl.addLayout(bar)
        fl.addWidget(self.files, 1)
        self.files_summary = QLabel("")
        self.files_summary.setObjectName("Muted")
        fl.addWidget(self.files_summary)

        # Options
        special = {
            tb.PageOrganizer: self._make_organizer,
            tb.Pipeline: self._make_pipeline,
        }
        self.form = OptionsForm(tool.options, special=special)
        saved = settings.get(f"tools/{tool.id}", {}) or {}
        remembered = {o.key: saved[o.key] for o in tool.options if o.remember and o.key in saved}
        if remembered:
            self.form.set_values(remembered)
        self.form.changed.connect(self._update_run_state)

        options_box = panel()
        ol = QVBoxLayout(options_box)
        ol.setContentsMargins(16, 16, 16, 16)
        if tool.options:
            heading = QLabel("Settings")
            heading.setObjectName("SectionTitle")
            ol.addWidget(heading)
            if has_organizer:
                ol.addWidget(self.form)
                for widget in self.form.external.values():
                    ol.addWidget(widget, 1)
            else:
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                holder = QWidget()
                hl = QVBoxLayout(holder)
                hl.setContentsMargins(0, 0, 4, 0)
                hl.addWidget(self.form)
                hl.addStretch(1)
                scroll.setWidget(holder)
                ol.addWidget(scroll, 1)
        else:
            note = QLabel("No settings needed. Add files and press the button below.")
            note.setObjectName("Muted")
            note.setWordWrap(True)
            ol.addWidget(note)
            ol.addStretch(1)

        splitter = QSplitter(Qt.Orientation.Vertical if has_organizer else Qt.Orientation.Horizontal)
        splitter.addWidget(files_box)
        splitter.addWidget(options_box)
        splitter.setChildrenCollapsible(False)
        if has_organizer:
            files_box.setMaximumHeight(150)
            self.files.list.setMinimumHeight(40)
            self.files.drop.setMinimumHeight(60)
            splitter.setSizes([130, 700])
        else:
            splitter.setSizes([560, 460])

        # Output
        out_box = panel()
        out = QVBoxLayout(out_box)
        out.setContentsMargins(16, 12, 16, 12)
        row = QHBoxLayout()
        row.addWidget(QLabel("<b>Save to</b>"))
        self.same_radio = QRadioButton("Same folder as the original")
        self.folder_radio = QRadioButton("")
        group = QButtonGroup(self)
        group.addButton(self.same_radio)
        group.addButton(self.folder_radio)
        self.folder_label = QLabel()
        self.folder_label.setObjectName("Muted")
        change = QPushButton("Change…")
        change.clicked.connect(self._choose_output_folder)
        row.addWidget(self.same_radio)
        row.addSpacing(10)
        row.addWidget(self.folder_radio)
        row.addWidget(self.folder_label, 1)
        row.addWidget(change)
        out.addLayout(row)
        self.output_dir = settings.output_folder()
        if settings.output_mode() == "folder":
            self.folder_radio.setChecked(True)
        else:
            self.same_radio.setChecked(True)
        self._show_folder()
        self.name_edit = None
        if tool.mode == tb.COMBINE and not tool.report:
            name_row = QHBoxLayout()
            name_row.addWidget(QLabel("<b>File name</b>"))
            self.name_edit = QLineEdit(tool.output_name)
            self.name_edit.setMaximumWidth(360)
            name_row.addWidget(self.name_edit)
            name_row.addWidget(QLabel(tool.output_ext))
            name_row.addStretch(1)
            out.addLayout(name_row)
        if tool.report:
            out_box.hide()

        # Run bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.runner.cancel)
        self.cancel_btn.hide()
        self.run_btn = QPushButton(self._action_label())
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self.start)
        run_row = QHBoxLayout()
        status_col = QVBoxLayout()
        status_col.addWidget(self.status)
        status_col.addWidget(self.progress)
        run_row.addLayout(status_col, 1)
        run_row.addWidget(self.cancel_btn)
        run_row.addWidget(self.run_btn)

        # Results
        self.results_box = panel()
        rl = QVBoxLayout(self.results_box)
        rl.setContentsMargins(16, 12, 16, 12)
        self.results_title = QLabel()
        self.results_title.setObjectName("Success")
        self.results_list = QListWidget()
        self.results_list.setMaximumHeight(112)
        self.results_list.itemDoubleClicked.connect(lambda item: self._open_item(item))
        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setMinimumHeight(220)
        self.report_view.hide()
        res_bar = QHBoxLayout()
        self.open_btn = QPushButton("Open")
        self.open_btn.setIcon(icons.icon("open", theme.current["text"], 16))
        self.open_btn.clicked.connect(self._open_selected)
        self.reveal_btn = QPushButton("Show in folder")
        self.reveal_btn.setIcon(icons.icon("folder", theme.current["text"], 16))
        self.reveal_btn.clicked.connect(self._reveal_selected)
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.report_view.toPlainText()))
        self.save_report_btn = QPushButton("Save as text…")
        self.save_report_btn.clicked.connect(self._save_report)
        close_results = QPushButton("Done")
        close_results.clicked.connect(self._close_results)
        for b in (self.open_btn, self.reveal_btn, self.copy_btn, self.save_report_btn):
            res_bar.addWidget(b)
        res_bar.addStretch(1)
        res_bar.addWidget(close_results)
        rl.addWidget(self.results_title)
        rl.addWidget(self.results_list)
        rl.addWidget(self.report_view)
        rl.addLayout(res_bar)
        self.results_box.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 16, 28, 20)
        layout.setSpacing(12)
        layout.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(header)
        layout.addWidget(self.warning)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.results_box)
        layout.addWidget(out_box)
        layout.addLayout(run_row)
        self._check_requirements()
        self._update_run_state()

    # -- building ------------------------------------------------------------

    def _make_organizer(self, opt):
        self.organizer = PageOrganizerWidget()
        return self.organizer

    def _make_pipeline(self, opt):
        self.pipeline = PipelineEditor()
        return self.pipeline

    def _action_label(self) -> str:
        if self.tool.report:
            return "Show information"
        verb = self.tool.name.split(" ")[0]
        return {"PDF": "Convert", "JPG/PNG": "Convert", "Word": "Convert", "Excel": "Convert",
                "PowerPoint": "Convert", "Batch": "Run batch", "OCR": "Make searchable", "Edit": "Save",
                "Header": "Add header and footer", "Page": "Add page numbers", "Extract": "Extract",
                "Watermark": "Add watermark", "Remove": "Remove password", "Reorder": "Save new order",
                "Grayscale": "Convert to grayscale"}.get(verb, self.tool.name)

    def _check_requirements(self):
        if self.tool.check:
            try:
                problem = self.tool.check()
            except Exception as exc:  # noqa: BLE001
                problem = str(exc)
            if problem:
                text = problem.replace("libreoffice.org", "<a href='https://www.libreoffice.org/download/'>"
                                                         "libreoffice.org</a>")
                self.warning.setText(text)
                self.warning.show()
                return
        self.warning.hide()

    # -- files ---------------------------------------------------------------

    def add_files(self, paths):
        added = self.files.add_paths(paths)
        rejected = getattr(self.files, "rejected", [])
        if rejected and not added:
            self.status.setText(f"{self.tool.name} works with {', '.join(self.tool.extensions)} files.")
        return added

    def _browse(self):
        patterns = " ".join(f"*{e}" for e in self.tool.extensions)
        label = tb.KIND_LABELS[self.tool.inputs[0]]
        last = settings.get("ui/last_dir", str(Path.home()))
        if self.tool.max_files == 1:
            path, _ = QFileDialog.getOpenFileName(self, "Choose a file", last, f"{label} ({patterns})")
            paths = [path] if path else []
        else:
            paths, _ = QFileDialog.getOpenFileNames(self, "Choose files", last, f"{label} ({patterns})")
        if paths:
            settings.put("ui/last_dir", str(Path(paths[0]).parent))
            self.add_files(paths)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder", settings.get("ui/last_dir", str(Path.home())))
        if folder:
            self.add_files([folder])

    def _files_changed(self):
        paths = self.files.paths()
        count = len(paths)
        pages = sum(self.files.info.get(p, {}).get("pages", 0) for p in paths)
        if count:
            text = f"{count} file{'s' if count != 1 else ''}"
            if pages:
                text += f", {pages} page{'s' if pages != 1 else ''}"
            self.files_summary.setText(text)
        else:
            self.files_summary.setText("")
        if self.organizer is not None:
            first = paths[0] if paths else None
            info = self.files.info.get(first, {}) if first else {}
            if first and info.get("locked") and first not in self.files.passwords:
                self.organizer.load(None)
                self.organizer.status.setText("This file needs its password. Press the button below to enter it.")
            else:
                self.organizer.load(first, self.files.passwords.get(first) if first else None)
        if self.tool.prefill and count == 1 and paths[0] in self.files.info:
            try:
                values = self.tool.prefill(paths[0], self.files.passwords.get(paths[0]))
                if values:
                    self.form.set_values(values)
            except Exception:  # noqa: BLE001
                pass
        self._update_run_state()

    def _update_run_state(self):
        count = len(self.files.paths())
        enough = count >= self.tool.min_files
        self.run_btn.setEnabled(enough and not self.runner.running)
        if not self.runner.running and not enough and count:
            self.status.setText(f"Add at least {self.tool.min_files} files.")
        elif not self.runner.running and self.status.text().startswith("Add at least"):
            self.status.setText("")

    # -- output --------------------------------------------------------------

    def _show_folder(self):
        self.folder_label.setText(self.output_dir)
        self.folder_radio.setText("This folder:")

    def _choose_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Save results to", self.output_dir)
        if folder:
            self.output_dir = folder
            self.folder_radio.setChecked(True)
            self._show_folder()
            settings.put("output/folder", folder)
            settings.put("output/mode", "folder")

    # -- running -------------------------------------------------------------

    def _ask_passwords(self) -> bool:
        import pikepdf

        if self.tool.id == "unlock" and self.form.values().get("password"):
            for path in self.files.locked_files():
                self.files.passwords[path] = self.form.values()["password"]
            return True
        for path in self.files.locked_files():
            while True:
                text, ok = QInputDialog.getText(self, "Password needed", f"Enter the password for\n{Path(path).name}",
                                                QLineEdit.EchoMode.Password)
                if not ok:
                    return False
                try:
                    pikepdf.open(path, password=text).close()
                except pikepdf.PasswordError:
                    QMessageBox.warning(self, "Wrong password", "That password is not correct. Please try again.")
                    continue
                except Exception:  # noqa: BLE001
                    pass
                self.files.passwords[path] = text
                self.files.refresh_item(path)
                break
        if self.organizer is not None:
            self._files_changed()
        return True

    def _remember(self, values):
        keep = {}
        for opt in self.tool.options:
            if not opt.remember:
                continue
            value = values.get(opt.key)
            if isinstance(opt, tb.Pipeline):
                from pdftoolbox.tools import get_tool

                cleaned = []
                for step in value or []:
                    tool = get_tool(step["tool"])
                    secret = {o.key for o in tool.options if isinstance(o, tb.Password)}
                    cleaned.append({"tool": step["tool"],
                                    "options": {k: v for k, v in step["options"].items() if k not in secret}})
                value = cleaned
            keep[opt.key] = value
        settings.put(f"tools/{self.tool.id}", keep)

    def start(self):
        if self.runner.running:
            return
        problems = self.form.problems()
        if problems:
            QMessageBox.warning(self, self.tool.name, problems[0])
            return
        if not self._ask_passwords():
            return
        values = self.form.values()
        self._remember(values)
        paths = self.files.paths()
        output_dir = self.output_dir if self.folder_radio.isChecked() else None
        settings.put("output/mode", "folder" if output_dir else "same")
        output_file = None
        if self.tool.mode == tb.COMBINE and not self.tool.report and self.name_edit is not None:
            folder = Path(output_dir or Path(paths[0]).parent)
            name = safe_name(self.name_edit.text().strip() or self.tool.output_name)
            if name.lower().endswith(self.tool.output_ext):
                name = name[: -len(self.tool.output_ext)]
            output_file = str(unique_path(folder / f"{name}{self.tool.output_ext}"))
        spec = JobSpec(self.tool.id, paths, values, output_dir=output_dir, output_file=output_file,
                       passwords=dict(self.files.passwords))
        self.results_box.hide()
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_btn.show()
        self.status.setObjectName("Muted")
        self.status.setText("Starting…")
        self.run_btn.setEnabled(False)
        self.started_at = time.monotonic()
        self.runner.start(spec)
        self.busy_changed.emit(True)

    def _end(self):
        self.progress.hide()
        self.cancel_btn.hide()
        self._update_run_state()
        self.busy_changed.emit(False)

    def _on_progress(self, fraction, message):
        self.progress.setValue(int(fraction * 1000))
        if message:
            self.status.setText(message)

    def _on_finished(self, results):
        self._end()
        elapsed = time.monotonic() - self.started_at
        ok = [r for r in results if not r.error]
        bad = [r for r in results if r.error]
        self.results_list.clear()
        reports = []
        for r in results:
            if r.report:
                reports.append(r.report)
            for out in r.outputs:
                item = QListWidgetItem(icons.icon("check", theme.current["success"], 16), Path(out).name)
                item.setData(Qt.ItemDataRole.UserRole, out)
                item.setToolTip(out)
                self.results_list.addItem(item)
            if r.message and not r.error:
                note = QListWidgetItem(r.message)
                note.setFlags(Qt.ItemFlag.ItemIsEnabled)
                note.setForeground(QApplication.palette().placeholderText())
                self.results_list.addItem(note)
            if r.error:
                item = QListWidgetItem(icons.icon("error", theme.current["danger"], 16),
                                       f"{Path(r.source).name}: {r.error}")
                item.setToolTip(r.message or r.error)
                self.results_list.addItem(item)
        outputs = [out for r in results for out in r.outputs]
        if self.tool.report:
            self.report_view.setPlainText(("\n\n" + "-" * 48 + "\n\n").join(reports))
        self.report_view.setVisible(self.tool.report and bool(reports))
        self.results_list.setVisible(self.results_list.count() > 0 and (not self.tool.report or bool(bad)))
        self.copy_btn.setVisible(self.tool.report)
        self.save_report_btn.setVisible(self.tool.report)
        self.open_btn.setVisible(bool(outputs))
        self.reveal_btn.setVisible(bool(outputs))
        if bad and not ok:
            self.results_title.setObjectName("Error")
            self.results_title.setText(f"Could not process {'the file' if len(bad) == 1 else 'the files'}.")
        elif bad:
            self.results_title.setObjectName("Error")
            self.results_title.setText(f"Finished with problems: {len(ok)} done, {len(bad)} failed.")
        else:
            self.results_title.setObjectName("Success")
            made = f"{len(outputs)} file{'s' if len(outputs) != 1 else ''} created" if outputs else "Done"
            self.results_title.setText(f"✓ {made} in {elapsed:.1f} s")
        self.results_title.style().polish(self.results_title)
        self.status.setText("")
        self.results_box.show()
        if self.results_list.count():
            self.results_list.setCurrentRow(0)
        if outputs and settings.open_when_done() and not bad:
            desktop.open_path(outputs[0])

    def _on_failed(self, message):
        self._end()
        first, _, details = message.partition("\n\n")
        self.status.setObjectName("Error")
        self.status.style().polish(self.status)
        self.status.setText(first)
        self.status.setToolTip(details)

    def _on_cancelled(self):
        self._end()
        self.status.setText("Cancelled. Files that were already finished have been kept.")

    # -- results -------------------------------------------------------------

    def _selected_output(self):
        item = self.results_list.currentItem()
        path = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not path:
            for i in range(self.results_list.count()):
                path = self.results_list.item(i).data(Qt.ItemDataRole.UserRole)
                if path:
                    break
        return path

    def _open_item(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            desktop.open_path(path)

    def _open_selected(self):
        path = self._selected_output()
        if path:
            desktop.open_path(path)

    def _reveal_selected(self):
        path = self._selected_output()
        if path:
            desktop.reveal(path)

    def _save_report(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save information", str(Path.home() / "PDF information.txt"),
                                              "Text (*.txt)")
        if path:
            Path(path).write_text(self.report_view.toPlainText(), encoding="utf-8")

    def _close_results(self):
        self.results_box.hide()
