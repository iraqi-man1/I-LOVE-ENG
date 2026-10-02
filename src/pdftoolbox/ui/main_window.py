"""Main window: sidebar, tool grid, tool screens and update notices."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from pdftoolbox import APP_NAME, __version__
from pdftoolbox.tools import all_tools
from pdftoolbox.tools import base as tb

from . import icons, settings, theme
from .dialogs import AboutDialog, SettingsDialog, UpdateCheck, UpdateDialog
from .widgets import FlowLayout

SCAN_ID = "__scan__"


class ToolCard(QFrame):
    clicked = Signal(str)

    def __init__(self, tool_id, name, description, icon_name, color):
        super().__init__()
        self.tool_id = tool_id
        self.setObjectName("ToolCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedSize(QSize(254, 112))
        badge = QLabel()
        badge.setPixmap(icons.badge(icon_name, color, 40))
        title = QLabel(name)
        title.setObjectName("ToolCardTitle")
        text = QLabel(description)
        text.setObjectName("ToolCardText")
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        right = QVBoxLayout()
        right.setSpacing(3)
        right.addWidget(title)
        right.addWidget(text, 1)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(12)
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(right, 1)
        self.setToolTip(description)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self.tool_id)
        super().mouseReleaseEvent(event)


class HomePage(QWidget):
    open_tool = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.setAcceptDrops(True)
        self.pending: list[str] = []
        self.tools = [t for t in all_tools() if not t.hidden]
        self.category = None

        title = QLabel("What would you like to do?")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Every tool works offline. Your files stay on this computer.")
        subtitle.setObjectName("PageSubtitle")
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Search tools  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icons.icon("search", theme.current["muted"], 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self.refilter)
        head = QHBoxLayout()
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(title)
        texts.addWidget(subtitle)
        head.addLayout(texts, 1)
        head.addWidget(self.search, 0, Qt.AlignmentFlag.AlignBottom)

        self.drop_banner = QFrame()
        self.drop_banner.setObjectName("Banner")
        bl = QHBoxLayout(self.drop_banner)
        bl.setContentsMargins(14, 10, 14, 10)
        self.drop_text = QLabel()
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_pending)
        bl.addWidget(self.drop_text, 1)
        bl.addWidget(clear)
        self.drop_banner.hide()

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 12, 12)
        self.content_layout.setSpacing(10)
        self.sections: list[tuple[QLabel, QWidget, list[ToolCard]]] = []
        groups = [("Scan", [(SCAN_ID, "Scan to PDF", "Scan paper documents from your scanner or printer into a PDF.",
                             "scan", icons.CATEGORY_COLORS["Scan"], ())])]
        for category in tb.CATEGORIES:
            entries = [(t.id, t.name, t.description, t.icon, icons.CATEGORY_COLORS[category], t)
                       for t in self.tools if t.category == category]
            groups.append((category, entries))
        for category, entries in groups:
            label = QLabel(category)
            label.setObjectName("SectionTitle")
            holder = QWidget()
            flow = FlowLayout(holder)
            cards = []
            for tool_id, name, desc, icon_name, color, tool in entries:
                card = ToolCard(tool_id, name, desc, icon_name, color)
                card.category = category
                card.tool = tool if isinstance(tool, tb.Tool) else None
                card.clicked.connect(self._clicked)
                flow.addWidget(card)
                cards.append(card)
            self.content_layout.addWidget(label)
            self.content_layout.addWidget(holder)
            self.sections.append((label, holder, cards))
        self.content_layout.addStretch(1)
        self.empty = QLabel("No tool matches your search.")
        self.empty.setObjectName("Muted")
        self.empty.hide()
        self.content_layout.insertWidget(0, self.empty)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 16, 8)
        layout.setSpacing(14)
        layout.addLayout(head)
        layout.addWidget(self.drop_banner)
        layout.addWidget(scroll, 1)

    def set_category(self, category):
        self.category = category
        self.refilter()

    def refilter(self):
        query = self.search.text().strip().lower()
        any_visible = False
        for label, holder, cards in self.sections:
            shown = 0
            for card in cards:
                tool = card.tool
                text = f"{card.findChild(QLabel, 'ToolCardTitle').text()} {card.toolTip()} " \
                       f"{tool.keywords if tool else 'scanner printer paper'}".lower()
                visible = (not query or all(word in text for word in query.split()))
                visible &= self.category in (None, card.category)
                if self.pending:
                    visible &= tool is not None and all(tool.accepts(p) for p in self.pending)
                card.setVisible(visible)
                shown += visible
            label.setVisible(shown > 0)
            holder.setVisible(shown > 0)
            holder.layout().invalidate()
            any_visible |= shown > 0
        self.empty.setVisible(not any_visible)

    def _clicked(self, tool_id):
        self.open_tool.emit(tool_id)

    def clear_pending(self):
        self.pending = []
        self.drop_banner.hide()
        self.refilter()

    def take_pending(self):
        files, self.pending = self.pending, []
        self.drop_banner.hide()
        self.refilter()
        return files

    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        files = []
        for p in paths:
            path = Path(p)
            files += [str(c) for c in sorted(path.rglob("*")) if c.is_file()] if path.is_dir() else [p]
        known = tuple(e for exts in tb.EXTENSIONS.values() for e in exts)
        files = [f for f in files if f.lower().endswith(known)]
        if not files:
            return
        self.pending = files
        n = len(files)
        self.drop_text.setText(f"<b>{n} file{'s' if n != 1 else ''} ready.</b> Choose what to do with "
                               f"{'it' if n == 1 else 'them'}.")
        self.drop_banner.show()
        self.search.clear()
        self.refilter()
        event.acceptProposedAction()


class MainWindow(QMainWindow):
    def __init__(self, files: list[str] | None = None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.resize(1240, 820)
        self.setMinimumSize(980, 640)
        self.pages: dict[str, QWidget] = {}
        self.busy: set[QWidget] = set()

        # Sidebar
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 0, 0)
        app_title = QLabel(APP_NAME)
        app_title.setObjectName("AppTitle")
        sl.addWidget(app_title)
        self.nav = QListWidget()
        self.nav.setIconSize(QSize(18, 18))
        entries = [("All tools", None, "grid"), ("Scan to PDF", SCAN_ID, "scan")]
        cat_icons = {"Organize": "reorder", "Convert": "image", "Edit": "header", "Optimize": "compress",
                     "Security": "lock"}
        entries += [(c, c, cat_icons[c]) for c in tb.CATEGORIES]
        for label, key, icon_name in entries:
            item = QListWidgetItem(icons.icon(icon_name, theme.current["muted"], 18), label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.nav.addItem(item)
        self.nav.setCurrentRow(0)
        self.nav.currentItemChanged.connect(self._nav)
        sl.addWidget(self.nav, 1)
        settings_btn = QPushButton("  Settings")
        settings_btn.setIcon(icons.icon("settings", theme.current["muted"], 16))
        settings_btn.setObjectName("Link")
        settings_btn.setStyleSheet(f"color: {theme.current['text']}; text-align: left; padding: 8px 18px;")
        settings_btn.clicked.connect(self.show_settings)
        sl.addWidget(settings_btn)
        self.footer = QLabel(f"Version {__version__} · Offline")
        self.footer.setObjectName("SidebarFooter")
        sl.addWidget(self.footer)

        # Update banner
        self.banner = QFrame()
        self.banner.setObjectName("Banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(14, 8, 14, 8)
        self.banner_text = QLabel()
        update_btn = QPushButton("Update now")
        update_btn.setObjectName("Primary")
        update_btn.clicked.connect(self._open_update)
        later = QPushButton("Later")
        later.clicked.connect(lambda: self.banner_wrap.hide())
        icon_label = QLabel()
        icon_label.setPixmap(icons.pixmap("update", theme.current["accent"], 18))
        bl.addWidget(icon_label)
        bl.addWidget(self.banner_text, 1)
        bl.addWidget(later)
        bl.addWidget(update_btn)
        self.banner.hide()
        self.release = None

        self.stack = QStackedWidget()
        self.home = HomePage()
        self.home.open_tool.connect(self.open_tool)
        self.stack.addWidget(self.home)

        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        banner_wrap = QWidget()
        bw = QVBoxLayout(banner_wrap)
        bw.setContentsMargins(20, 12, 20, 0)
        bw.addWidget(self.banner)
        self.banner_wrap = banner_wrap
        banner_wrap.hide()
        ml.addWidget(banner_wrap)
        ml.addWidget(self.stack, 1)

        central = QWidget()
        cl = QHBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(sidebar)
        cl.addWidget(main, 1)
        self.setCentralWidget(central)
        self._menus()

        self.checker = None
        if settings.auto_update():
            QTimer.singleShot(4000, lambda: self.check_updates(manual=False))
            self.update_timer = QTimer(self)
            self.update_timer.setInterval(6 * 60 * 60 * 1000)
            self.update_timer.timeout.connect(lambda: self.check_updates(manual=False))
            self.update_timer.start()
        if files:
            QTimer.singleShot(0, lambda: self._open_files(files))

    # -- menus ---------------------------------------------------------------

    def _menus(self):
        file_menu = self.menuBar().addMenu("&File")
        open_action = QAction("Open PDF files…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._open_dialog)
        file_menu.addAction(open_action)
        home_action = QAction("All tools", self)
        home_action.setShortcut(QKeySequence("Ctrl+Home"))
        home_action.triggered.connect(self.go_home)
        file_menu.addAction(home_action)
        file_menu.addSeparator()
        prefs = QAction("Settings…", self)
        prefs.setMenuRole(QAction.MenuRole.PreferencesRole)
        prefs.setShortcut(QKeySequence.StandardKey.Preferences)
        prefs.triggered.connect(self.show_settings)
        file_menu.addAction(prefs)
        quit_action = QAction("Quit", self)
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        find = QAction("Find a tool", self)
        find.setShortcut(QKeySequence.StandardKey.Find)
        find.triggered.connect(lambda: (self.go_home(), self.home.search.setFocus()))
        self.addAction(find)
        help_menu = self.menuBar().addMenu("&Help")
        check = QAction("Check for updates…", self)
        check.setMenuRole(QAction.MenuRole.ApplicationSpecificRole)
        check.triggered.connect(lambda: self.check_updates(manual=True))
        help_menu.addAction(check)
        about = QAction(f"About {APP_NAME}", self)
        about.setMenuRole(QAction.MenuRole.AboutRole)
        about.triggered.connect(lambda: AboutDialog(self).exec())
        help_menu.addAction(about)

    # -- navigation ----------------------------------------------------------

    def _nav(self, item, _previous=None):
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key == SCAN_ID:
            self.open_tool(SCAN_ID)
            return
        self.home.set_category(key)
        self.stack.setCurrentWidget(self.home)

    def go_home(self):
        self.stack.setCurrentWidget(self.home)
        if self.nav.currentRow() == 1:
            self.nav.blockSignals(True)
            self.nav.setCurrentRow(0)
            self.nav.blockSignals(False)
            self.home.set_category(None)

    def open_tool(self, tool_id: str, files: list[str] | None = None):
        page = self.pages.get(tool_id)
        if page is None:
            if tool_id == SCAN_ID:
                from .scan_page import ScanPage

                page = ScanPage()
            else:
                from pdftoolbox.tools import get_tool

                from .tool_page import ToolPage

                page = ToolPage(get_tool(tool_id))
            page.back.connect(self.go_home)
            page.busy_changed.connect(lambda busy, p=page: self._busy(p, busy))
            self.pages[tool_id] = page
            self.stack.addWidget(page)
        pending = files if files is not None else self.home.take_pending()
        if pending and hasattr(page, "add_files"):
            page.add_files(pending)
        self.stack.setCurrentWidget(page)
        if tool_id == SCAN_ID and self.nav.currentRow() != 1:
            self.nav.blockSignals(True)
            self.nav.setCurrentRow(1)
            self.nav.blockSignals(False)

    def _open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Open PDF files", settings.get("ui/last_dir", str(Path.home())),
                                                "PDF files (*.pdf);;All supported files (*.*)")
        if paths:
            settings.put("ui/last_dir", str(Path(paths[0]).parent))
            self._open_files(paths)

    def _open_files(self, files):
        current = self.stack.currentWidget()
        if hasattr(current, "add_files"):
            current.add_files(files)
            return
        self.stack.setCurrentWidget(self.home)
        self.home.pending = [f for f in files if Path(f).is_file()]
        if self.home.pending:
            n = len(self.home.pending)
            self.home.drop_text.setText(f"<b>{n} file{'s' if n != 1 else ''} ready.</b> Choose what to do with "
                                        f"{'it' if n == 1 else 'them'}.")
            self.home.drop_banner.show()
            self.home.refilter()

    # -- busy state ----------------------------------------------------------

    def _busy(self, page, busy):
        if busy:
            self.busy.add(page)
        else:
            self.busy.discard(page)

    def is_busy(self) -> bool:
        return bool(self.busy)

    def closeEvent(self, event):  # noqa: N802
        if self.busy:
            answer = QMessageBox.question(self, APP_NAME, "A task is still running. Stop it and quit?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        for page in self.pages.values():
            runner = getattr(page, "runner", None)
            if runner is not None and runner.running:
                runner.cancel()
                runner._kill()
            if hasattr(page, "cleanup"):
                page.cleanup()
        event.accept()

    # -- settings and updates ------------------------------------------------

    def show_settings(self):
        SettingsDialog(self).exec()

    def check_updates(self, manual: bool):
        if self.checker is not None:
            return
        self.checker = UpdateCheck()
        self.checker.found.connect(lambda r: self._update_found(r, manual))
        if manual:
            self.checker.none.connect(lambda: QMessageBox.information(
                self, "Updates", f"You have the latest version ({__version__})."))
            self.checker.error.connect(lambda m: QMessageBox.information(
                self, "Updates", "Could not check for updates. Check your internet connection and try again.\n\n" + m))
        self.checker.finished.connect(self._checker_done)
        self.checker.start()

    def _checker_done(self):
        self.checker = None

    def _update_found(self, release, manual):
        self.release = release
        if not manual and settings.get("updates/skipped") == release.version:
            return
        self.banner_text.setText(f"<b>{APP_NAME} {release.version}</b> is available. You have {__version__}.")
        self.banner_wrap.show()
        self.banner.show()
        self.footer.setText(f"Version {__version__} · Update available")
        if manual:
            self._open_update()

    def _open_update(self):
        if self.release:
            UpdateDialog(self.release, self).exec()
