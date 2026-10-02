"""macOS scanning through Image Capture (ImageCaptureCore).

ImageCaptureCore finds USB, network (Bonjour) and shared scanners, including
driverless AirScan devices, without any extra software. Its callbacks arrive
on the main thread, so every call into it is posted to the main thread and
the scanning thread waits for the result.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from .base import BW, COLOR, DUPLEX, FEEDER, FLATBED, GRAY, PAGE_SIZES, ScanBackend, ScanError, ScannerInfo

_state = {"browser": None, "delegate": None, "devices": {}}


def _frameworks():
    import ImageCaptureCore as ICC  # noqa: N811
    import objc
    from Foundation import NSURL, NSObject

    return ICC, objc, NSObject, NSURL


def _on_main(fn):
    """Run ``fn`` on the main thread and wait for it."""
    from PyObjCTools import AppHelper

    if threading.current_thread() is threading.main_thread():
        return fn()
    done = threading.Event()
    box = {}

    def call():
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc
        finally:
            done.set()

    AppHelper.callAfter(call)
    if not done.wait(30):
        raise ScanError("The scanning service did not respond.")
    if "error" in box:
        raise box["error"]
    return box.get("value")


_classes = {}


def _delegate_classes():
    if _classes:
        return _classes
    ICC, objc, NSObject, NSURL = _frameworks()

    class PTBrowserDelegate(NSObject):
        def deviceBrowser_didAddDevice_moreComing_(self, browser, device, more):
            _state["devices"][str(device.UUIDString())] = device

        def deviceBrowser_didRemoveDevice_moreGoing_(self, browser, device, more):
            _state["devices"].pop(str(device.UUIDString()), None)

    class PTScannerDelegate(NSObject):
        def initWithJob_(self, job):
            self = objc.super(PTScannerDelegate, self).init()
            if self is None:
                return None
            self.job = job
            return self

        # ICDeviceDelegate
        def device_didOpenSessionWithError_(self, device, error):
            self.job.event("open", error)

        def device_didCloseSessionWithError_(self, device, error):
            self.job.event("close", error)

        def didRemoveDevice_(self, device):
            self.job.event("removed", None)

        def device_didEncounterError_(self, device, error):
            self.job.event("error", error)

        # ICScannerDeviceDelegate
        def scannerDevice_didSelectFunctionalUnit_error_(self, scanner, unit, error):
            self.job.event("unit", error)

        def scannerDevice_didScanToURL_(self, scanner, url):
            self.job.page(str(url.path()))

        def scannerDevice_didCompleteScanWithError_(self, scanner, error):
            self.job.event("complete", error)

        def scannerDeviceDidBecomeAvailable_(self, scanner):
            self.job.event("available", None)

    _classes.update(browser=PTBrowserDelegate, scanner=PTScannerDelegate)
    return _classes


class _Job:
    def __init__(self, on_page):
        self.events: dict[str, object] = {}
        self.cond = threading.Condition()
        self.on_page = on_page
        self.pages = 0

    def event(self, name, error):
        with self.cond:
            self.events[name] = error
            self.cond.notify_all()

    def page(self, path):
        self.pages += 1
        self.on_page(Path(path))

    def wait(self, name, timeout, is_cancelled=lambda: False):
        deadline = time.monotonic() + timeout
        with self.cond:
            while name not in self.events:
                if "removed" in self.events:
                    raise ScanError("The scanner was disconnected.")
                if is_cancelled():
                    return None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ScanError("The scanner did not respond in time.")
                self.cond.wait(min(0.25, remaining))
            error = self.events.pop(name)
        if error is not None:
            raise ScanError(str(error.localizedDescription()))
        return True


class IcaBackend(ScanBackend):
    name = "Image Capture"

    def unavailable_reason(self):
        try:
            _frameworks()
        except Exception:  # noqa: BLE001
            return "Image Capture is not available."
        return None

    def _start_browser(self):
        ICC, _, _, _ = _frameworks()
        if _state["browser"] is not None:
            return

        def start():
            delegate = _delegate_classes()["browser"].alloc().init()
            browser = ICC.ICDeviceBrowser.alloc().init()
            browser.setDelegate_(delegate)
            mask = (ICC.ICDeviceTypeMaskScanner | ICC.ICDeviceLocationTypeMaskLocal
                    | ICC.ICDeviceLocationTypeMaskShared | ICC.ICDeviceLocationTypeMaskBonjour
                    | ICC.ICDeviceLocationTypeMaskRemote)
            browser.setBrowsedDeviceTypeMask_(mask)
            browser.start()
            _state["browser"], _state["delegate"] = browser, delegate

        _on_main(start)

    def list_devices(self):
        first = _state["browser"] is None
        self._start_browser()
        # Network scanners take a moment to announce themselves.
        time.sleep(3.0 if first else 0.5)
        ICC, _, _, _ = _frameworks()
        result = []
        for uid, device in list(_state["devices"].items()):

            def describe(device=device):
                units = [int(u) for u in (device.availableFunctionalUnitTypes() or [])]
                return str(device.name()), units

            name, units = _on_main(describe)
            sources = []
            if ICC.ICScannerFunctionalUnitTypeFlatbed in units or not units:
                sources.append(FLATBED)
            if ICC.ICScannerFunctionalUnitTypeDocumentFeeder in units:
                sources += [FEEDER, DUPLEX]
            result.append(ScannerInfo(uid, name, sources))
        return result

    def scan(self, device, settings, folder: Path, on_page, is_cancelled):
        ICC, _, _, NSURL = _frameworks()
        scanner = _state["devices"].get(device.id)
        if scanner is None:
            raise ScanError("The scanner is no longer available. Click Refresh.")
        job = _Job(on_page)
        delegate = _on_main(lambda: _delegate_classes()["scanner"].alloc().initWithJob_(job))
        use_feeder = settings.source in (FEEDER, DUPLEX)
        unit_type = ICC.ICScannerFunctionalUnitTypeDocumentFeeder if use_feeder else ICC.ICScannerFunctionalUnitTypeFlatbed

        def open_session():
            scanner.setDelegate_(delegate)
            scanner.requestOpenSession()

        _on_main(open_session)
        try:
            job.wait("open", 30)
            _on_main(lambda: scanner.requestSelectFunctionalUnit_(unit_type))
            try:
                job.wait("unit", 20)
            except ScanError:
                if use_feeder:
                    raise ScanError("This scanner has no document feeder.") from None
                raise

            def configure():
                unit = scanner.selectedFunctionalUnit()
                unit.setMeasurementUnit_(ICC.ICScannerMeasurementUnitInches)
                resolutions = unit.supportedResolutions()
                dpi = settings.dpi
                if resolutions is not None and resolutions.count():
                    values = []
                    index = resolutions.firstIndex()
                    while index != 0x7FFFFFFFFFFFFFFF and len(values) < 10000:  # NSNotFound
                        values.append(int(index))
                        index = resolutions.indexGreaterThanIndex_(index)
                    if values and dpi not in values:
                        dpi = min(values, key=lambda v: abs(v - dpi))
                unit.setResolution_(dpi)
                if settings.color == BW:
                    unit.setPixelDataType_(ICC.ICScannerPixelDataTypeBW)
                    unit.setBitDepth_(ICC.ICScannerBitDepth1Bit)
                elif settings.color == GRAY:
                    unit.setPixelDataType_(ICC.ICScannerPixelDataTypeGray)
                    unit.setBitDepth_(ICC.ICScannerBitDepth8Bits)
                else:
                    unit.setPixelDataType_(ICC.ICScannerPixelDataTypeRGB)
                    unit.setBitDepth_(ICC.ICScannerBitDepth8Bits)
                if use_feeder:
                    names = {"a4": "ICScannerDocumentTypeA4", "letter": "ICScannerDocumentTypeUSLetter",
                             "legal": "ICScannerDocumentTypeUSLegal", "a5": "ICScannerDocumentTypeA5"}
                    doc_type = getattr(ICC, names.get(settings.page, ""), None)
                    unit.setDocumentType_(doc_type if doc_type is not None else ICC.ICScannerDocumentTypeDefault)
                    if unit.supportsDuplexScanning():
                        unit.setDuplexScanningEnabled_(settings.source == DUPLEX)
                else:
                    size = unit.physicalSize()
                    width, height = size.width, size.height
                    if settings.page in PAGE_SIZES:
                        w_in, h_in = PAGE_SIZES[settings.page]
                        width, height = min(width, w_in), min(height, h_in)
                    unit.setScanArea_(((0.0, 0.0), (width, height)))
                scanner.setTransferMode_(ICC.ICScannerTransferModeFileBased)
                scanner.setDownloadsDirectory_(NSURL.fileURLWithPath_(str(folder)))
                scanner.setDocumentName_(f"scan-{int(time.time() * 1000)}")
                scanner.setDocumentUTI_("public.png")
                scanner.requestScan()

            _on_main(configure)
            finished = job.wait("complete", 1800, is_cancelled)
            if finished is None:
                _on_main(lambda: scanner.cancelScan())
                job.wait("complete", 30)
        finally:
            _on_main(lambda: scanner.requestCloseSession())
        if job.pages == 0 and not is_cancelled():
            raise ScanError("No pages were scanned." + (" Is there paper in the feeder?" if use_feeder else ""))
        return job.pages
