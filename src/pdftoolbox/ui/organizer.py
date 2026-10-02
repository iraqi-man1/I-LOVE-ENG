"""Visual page organiser: drag pages, rotate, delete."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem, QPushButton, QSlider,
    QVBoxLayout, QWidget,
)

from . import icons, theme
from .thumbnails import ThumbnailService

ROLE_PAGE = Qt.ItemDataRole.UserRole
ROLE_ROTATE = Qt.ItemDataRole.UserRole + 1


class PageGrid(QListWidget):
    """Icon grid of pages that can be dragged into a new order."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setMovement(QListView.Movement.Snap)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setWrapping(True)
        self.setSpacing(10)
        self.setUniformItemSizes(True)
        self.set_thumb_size(140)

    def set_thumb_size(self, size: int):
        self.thumb = size
        self.setIconSize(QSize(size, size))
        self.setGridSize(QSize(size + 24, size + 40))


def placeholder(size: int) -> QPixmap:
    pm = QPixmap(int(size * 0.72), size)
    pm.fill(QColor(theme.current["surface2"]))
    return pm


def rotated(image: QImage, degrees: int) -> QPixmap:
    pm = QPixmap.fromImage(image)
    if degrees % 360:
        pm = pm.transformed(QTransform().rotate(degrees), Qt.TransformationMode.SmoothTransformation)
    return pm


class PageOrganizerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.path: str | None = None
        self.password: str | None = None
        self.images: dict[int, QImage] = {}
        self.requested: set[int] = set()
        self.service = ThumbnailService.instance()
        self.service.ready.connect(self._on_ready)
        self.service.opened.connect(self._on_opened)
        self.service.failed.connect(self._on_failed)

        self.grid = PageGrid()
        self.grid.verticalScrollBar().valueChanged.connect(lambda *_: self._schedule())
        self.grid.setMinimumHeight(150)
        self.status = QLabel("Add a PDF to see its pages.")
        self.status.setObjectName("Muted")

        bar = QHBoxLayout()

        def button(text, icon_name, slot, tip=""):
            b = QPushButton(text)
            if icon_name:
                b.setIcon(icons.icon(icon_name, theme.current["text"], 16))
            b.setToolTip(tip)
            b.clicked.connect(slot)
            bar.addWidget(b)
            return b

        button("", "rotate_left", lambda: self.rotate(-90), "Rotate selected pages left")
        button("", "rotate", lambda: self.rotate(90), "Rotate selected pages right")
        button("Delete", "trash", self.delete_selected, "Remove selected pages")
        button("Reverse", None, self.reverse, "Reverse the page order")
        button("Reset", None, self.reset, "Undo all changes")
        bar.addStretch(1)
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(80, 260)
        self.zoom.setValue(140)
        self.zoom.setFixedWidth(120)
        self.zoom.valueChanged.connect(self._zoom)
        bar.addWidget(QLabel("Size"))
        bar.addWidget(self.zoom)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(bar)
        layout.addWidget(self.grid, 1)
        layout.addWidget(self.status)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._request_visible)

    # Option widget protocol
    def value(self):
        return [{"page": self.grid.item(i).data(ROLE_PAGE), "rotate": self.grid.item(i).data(ROLE_ROTATE)}
                for i in range(self.grid.count())]

    def set_value(self, value):
        pass

    def load(self, path: str | None, password: str | None = None):
        if path == self.path and password == self.password:
            return
        self.path, self.password = path, password
        self.grid.clear()
        self.images.clear()
        self.requested.clear()
        if not path:
            self.status.setText("Add a PDF to see its pages.")
            return
        self.status.setText("Loading pages…")
        self.service.open(path, password)

    def _on_opened(self, path, count):
        if path != self.path:
            return
        ph = QIcon(placeholder(self.grid.thumb))
        self.grid.setUpdatesEnabled(False)
        for i in range(count):
            item = QListWidgetItem(ph, str(i + 1))
            item.setData(ROLE_PAGE, i)
            item.setData(ROLE_ROTATE, 0)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.grid.addItem(item)
        self.grid.setUpdatesEnabled(True)
        self.status.setText(f"{count} pages. Drag to reorder; select several with Ctrl/⌘ or Shift.")
        self._schedule()

    def _on_failed(self, path, message):
        if path == self.path:
            self.status.setText(f"Could not show pages: {message}")

    def _schedule(self):
        self._timer.start()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self._schedule()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._schedule()

    def _request_visible(self):
        if not self.path or not self.grid.count():
            return
        rect = self.grid.viewport().rect()
        first = self.grid.indexAt(rect.topLeft() + QPoint(5, 5))
        start = max(0, first.row() if first.isValid() else 0)
        per_row = max(1, rect.width() // self.grid.gridSize().width())
        rows = rect.height() // self.grid.gridSize().height() + 2
        end = min(self.grid.count(), start + per_row * rows + per_row)
        # Request in reverse so the top of the view arrives first (LIFO queue).
        for row in range(end - 1, start - 1, -1):
            page = self.grid.item(row).data(ROLE_PAGE)
            if page not in self.requested:
                self.requested.add(page)
                self.service.request(self.path, page, 260, self.password)

    def _on_ready(self, path, index, image):
        if path != self.path:
            return
        self.images[index] = image
        for row in range(self.grid.count()):
            item = self.grid.item(row)
            if item.data(ROLE_PAGE) == index:
                self._paint(item)

    def _paint(self, item):
        image = self.images.get(item.data(ROLE_PAGE))
        if image is None:
            return
        pm = rotated(image, item.data(ROLE_ROTATE))
        pm = pm.scaled(self.grid.thumb, self.grid.thumb, Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
        framed = QPixmap(pm.size())
        framed.fill(Qt.GlobalColor.white)
        p = QPainter(framed)
        p.drawPixmap(0, 0, pm)
        p.setPen(QColor(theme.current["border"]))
        p.drawRect(0, 0, pm.width() - 1, pm.height() - 1)
        p.end()
        item.setIcon(QIcon(framed))

    def rotate(self, degrees):
        for item in self.grid.selectedItems() or []:
            item.setData(ROLE_ROTATE, (item.data(ROLE_ROTATE) + degrees) % 360)
            self._paint(item)

    def delete_selected(self):
        for item in self.grid.selectedItems():
            self.grid.takeItem(self.grid.row(item))
        self.status.setText(f"{self.grid.count()} pages will be saved.")

    def reverse(self):
        items = [self.grid.takeItem(0) for _ in range(self.grid.count())]
        for item in reversed(items):
            self.grid.addItem(item)

    def reset(self):
        path, password = self.path, self.password
        self.path = None
        self.load(path, password)

    def _zoom(self, value):
        self.grid.set_thumb_size(value)
        for row in range(self.grid.count()):
            self._paint(self.grid.item(row))
        self._schedule()
