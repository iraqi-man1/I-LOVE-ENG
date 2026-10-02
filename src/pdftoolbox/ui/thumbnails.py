"""Background page thumbnails rendered with PDFium on a single worker thread."""

from __future__ import annotations

import queue
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage


class ThumbnailService(QObject):
    ready = Signal(str, int, QImage)  # path, page index, image
    opened = Signal(str, int)  # path, page count
    failed = Signal(str, str)

    _instance = None

    @classmethod
    def instance(cls) -> "ThumbnailService":
        if cls._instance is None:
            cls._instance = ThumbnailService()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._requests: queue.LifoQueue = queue.LifoQueue()
        self._generation = 0
        self._thread = threading.Thread(target=self._loop, name="thumbnails", daemon=True)
        self._thread.start()

    def open(self, path: str, password: str | None = None) -> None:
        self._generation += 1
        self._requests.put(("open", self._generation, path, password, 0, 0))

    def request(self, path: str, index: int, size: int, password: str | None = None) -> None:
        self._requests.put(("page", self._generation, path, password, index, size))

    def _loop(self):
        import pypdfium2 as pdfium

        docs: dict[str, object] = {}
        while True:
            kind, generation, path, password, index, size = self._requests.get()
            if generation != self._generation and kind == "page":
                continue  # a different file was opened since
            try:
                doc = docs.get(path)
                if doc is None:
                    for old in docs.values():
                        old.close()
                    docs.clear()
                    doc = pdfium.PdfDocument(path, password=password or None)
                    docs[path] = doc
                if kind == "open":
                    self.opened.emit(path, len(doc))
                    continue
                page = doc[index]
                try:
                    w, h = page.get_size()
                    scale = size / max(w, h)
                    pil = page.render(scale=scale, draw_annots=True).to_pil().convert("RGB")
                finally:
                    page.close()
                data = pil.tobytes("raw", "RGB")
                image = QImage(data, pil.width, pil.height, pil.width * 3, QImage.Format.Format_RGB888).copy()
                self.ready.emit(path, index, image)
            except Exception as exc:  # noqa: BLE001
                self.failed.emit(path, str(exc))
