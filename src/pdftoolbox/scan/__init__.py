"""Scanner support.

Each platform uses the scanning service built into the operating system, so
any scanner or multifunction printer with a normal driver works:

* Windows: WIA (Windows Image Acquisition)
* macOS: Image Capture (ImageCaptureCore), including network and AirScan devices
* Linux: SANE (for development)
"""

from __future__ import annotations

import os
import sys

from .base import ScanBackend, ScanError, ScannerInfo, ScanSettings  # noqa: F401


def get_backend() -> ScanBackend:
    if os.environ.get("PDFTOOLBOX_FAKE_SCANNER"):
        from .fake import FakeBackend

        return FakeBackend()
    if sys.platform.startswith("win"):
        from .wia import WiaBackend

        return WiaBackend()
    if sys.platform == "darwin":
        from .ica import IcaBackend

        return IcaBackend()
    from .sane import SaneBackend

    return SaneBackend()
