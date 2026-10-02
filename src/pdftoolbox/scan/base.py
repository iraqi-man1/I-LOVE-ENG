from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

FLATBED = "flatbed"
FEEDER = "feeder"
DUPLEX = "duplex"

COLOR = "color"
GRAY = "gray"
BW = "bw"

# Page sizes in inches.
PAGE_SIZES = {"a4": (8.27, 11.69), "letter": (8.5, 11.0), "legal": (8.5, 14.0), "a5": (5.83, 8.27)}


class ScanError(Exception):
    """A problem to show to the user (no paper, scanner busy...)."""


@dataclass
class ScannerInfo:
    id: str
    name: str
    sources: list[str] = field(default_factory=lambda: [FLATBED])
    detail: str = ""


@dataclass
class ScanSettings:
    source: str = FLATBED
    color: str = COLOR
    dpi: int = 200
    page: str = "a4"  # a key of PAGE_SIZES or "max" for the whole scan area


PageCallback = Callable[[Path], None]


class ScanBackend:
    name = "scanner"

    def unavailable_reason(self) -> str | None:
        """Why scanning cannot work on this computer, or None."""
        return None

    def list_devices(self) -> list[ScannerInfo]:
        """Find connected scanners. May take a few seconds; call off the UI thread."""
        raise NotImplementedError

    def scan(self, device: ScannerInfo, settings: ScanSettings, folder: Path, on_page: PageCallback,
             is_cancelled: Callable[[], bool]) -> int:
        """Scan one page (flatbed) or every page in the feeder. Returns the page count."""
        raise NotImplementedError
