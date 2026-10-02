"""A pretend scanner for trying the interface without hardware."""

from __future__ import annotations

import time
from pathlib import Path

from PIL import Image, ImageDraw

from .base import BW, FEEDER, FLATBED, GRAY, PAGE_SIZES, ScanBackend, ScannerInfo


class FakeBackend(ScanBackend):
    name = "demo"
    _count = 0

    def list_devices(self):
        time.sleep(0.3)
        return [ScannerInfo("fake", "Demo scanner (no hardware)", [FLATBED, FEEDER])]

    def scan(self, device, settings, folder, on_page, is_cancelled):
        pages = 3 if settings.source != FLATBED else 1
        w_in, h_in = PAGE_SIZES.get(settings.page, PAGE_SIZES["a4"])
        for _ in range(pages):
            if is_cancelled():
                break
            time.sleep(0.4)
            FakeBackend._count += 1
            dpi = min(settings.dpi, 150)
            mode = "L" if settings.color in (GRAY, BW) else "RGB"
            image = Image.new(mode, (int(w_in * dpi), int(h_in * dpi)), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((dpi // 2, dpi // 2, image.width - dpi // 2, dpi), fill="black" if mode == "L" else "navy")
            draw.text((dpi // 2, int(dpi * 1.3)), f"Scanned page {FakeBackend._count}", fill="black")
            if settings.color == BW:
                image = image.convert("1")
            path = folder / f"demo-{FakeBackend._count}.png"
            image.save(path, dpi=(dpi, dpi))
            on_page(path)
        return pages
