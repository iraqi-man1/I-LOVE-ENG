"""Windows scanning through WIA (Windows Image Acquisition).

WIA ships with every version of Windows and works with any scanner or
multifunction printer whose driver supports it (nearly all of them, including
network devices added through Settings > Bluetooth & devices).
"""

from __future__ import annotations

import time
from pathlib import Path

from .base import BW, COLOR, DUPLEX, FEEDER, FLATBED, GRAY, PAGE_SIZES, ScanBackend, ScanError, ScannerInfo

SCANNER_DEVICE_TYPE = 1
FORMAT_PNG = "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}"
FORMAT_BMP = "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}"

# Device properties
DOCUMENT_HANDLING_CAPABILITIES = 3086
DOCUMENT_HANDLING_STATUS = 3087
DOCUMENT_HANDLING_SELECT = 3088
PAGES = 3096
# Item properties
CURRENT_INTENT = 6146
HORIZONTAL_RESOLUTION = 6147
VERTICAL_RESOLUTION = 6148
HORIZONTAL_START = 6149
VERTICAL_START = 6150
HORIZONTAL_EXTENT = 6151
VERTICAL_EXTENT = 6152
DATA_TYPE = 4103
BITS_PER_PIXEL = 4104

FEED, FLAT, DUP = 0x001, 0x002, 0x004

ERRORS = {
    0x80210001: "The scanner reported a general error. Check it is switched on and connected.",
    0x80210002: "Paper is jammed in the scanner.",
    0x80210003: "There is no paper in the document feeder.",
    0x80210004: "The scanner needs attention (check its display or lid).",
    0x80210005: "The scanner is offline. Check that it is switched on and connected.",
    0x80210006: "The scanner is busy. Wait a moment and try again.",
    0x80210007: "The scanner is warming up. Wait a moment and try again.",
    0x8021000A: "The scanner's cover is open.",
    0x8021000C: "The scanner lamp is off.",
    0x80210015: "The scanner was not found. Check the connection and click Refresh.",
    0x80210064: "Scanning was cancelled on the scanner.",
}
PAPER_EMPTY = 0x80210003


def _hresult(exc) -> int | None:
    try:
        code = exc.excepinfo[5] if getattr(exc, "excepinfo", None) else exc.hresult
    except Exception:  # noqa: BLE001
        try:
            code = exc.args[2][5] if exc.args[2] else exc.args[0]
        except Exception:  # noqa: BLE001
            return None
    return code & 0xFFFFFFFF if isinstance(code, int) else None


def _set(props, prop_id: int, value) -> bool:
    try:
        prop = props.Item(str(prop_id))
    except Exception:  # noqa: BLE001 - property not supported by this driver
        return False
    try:
        if prop.IsReadOnly:
            return False
        sub_type = prop.SubType  # 0 unspecified, 1 range, 2 list, 3 flag
        if sub_type == 1 and isinstance(value, (int, float)):
            lo, hi = prop.SubTypeMin, prop.SubTypeMax
            step = prop.SubTypeStep or 1
            value = max(lo, min(hi, value))
            value = lo + round((value - lo) / step) * step
        elif sub_type == 2 and isinstance(value, (int, float)):
            options = [prop.SubTypeValues.Item(i) for i in range(1, prop.SubTypeValues.Count + 1)]
            if options and value not in options:
                value = min(options, key=lambda v: abs(v - value))
        prop.Value = value
        return True
    except Exception:  # noqa: BLE001
        return False


def _get(props, prop_id: int, default=None):
    try:
        return props.Item(str(prop_id)).Value
    except Exception:  # noqa: BLE001
        return default


class WiaBackend(ScanBackend):
    name = "WIA"

    def _manager(self):
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        return win32com.client.Dispatch("WIA.DeviceManager")

    def unavailable_reason(self):
        try:
            self._manager()
        except Exception:  # noqa: BLE001
            return "Windows Image Acquisition (WIA) is not available on this computer."
        return None

    def list_devices(self):
        manager = self._manager()
        devices = []
        infos = manager.DeviceInfos
        for i in range(1, infos.Count + 1):
            info = infos.Item(i)
            if info.Type != SCANNER_DEVICE_TYPE:
                continue
            try:
                name = info.Properties.Item("Name").Value
            except Exception:  # noqa: BLE001
                name = "Scanner"
            sources = [FLATBED]
            try:
                device = info.Connect()
                caps = _get(device.Properties, DOCUMENT_HANDLING_CAPABILITIES, 0) or 0
                sources = []
                if caps & FLAT or not caps:
                    sources.append(FLATBED)
                if caps & FEED:
                    sources.append(FEEDER)
                if caps & DUP:
                    sources.append(DUPLEX)
            except Exception:  # noqa: BLE001 - offline devices still appear in the list
                pass
            devices.append(ScannerInfo(info.DeviceID, str(name), sources or [FLATBED]))
        return devices

    def scan(self, device, settings, folder: Path, on_page, is_cancelled):
        import pywintypes

        manager = self._manager()
        wia_device = None
        infos = manager.DeviceInfos
        for i in range(1, infos.Count + 1):
            info = infos.Item(i)
            if info.DeviceID == device.id:
                try:
                    wia_device = info.Connect()
                except pywintypes.com_error as exc:
                    raise ScanError(ERRORS.get(_hresult(exc), "The scanner could not be opened.")) from None
                break
        if wia_device is None:
            raise ScanError("The scanner is no longer connected. Click Refresh.")

        use_feeder = settings.source in (FEEDER, DUPLEX)
        select = FLAT
        if use_feeder:
            select = FEED | (DUP if settings.source == DUPLEX else 0)
        _set(wia_device.Properties, DOCUMENT_HANDLING_SELECT, select)
        if use_feeder:
            _set(wia_device.Properties, PAGES, 0)  # 0 = every page in the feeder

        item = wia_device.Items.Item(1)
        props = item.Properties
        intent = {COLOR: 1, GRAY: 2, BW: 4}[settings.color]
        _set(props, CURRENT_INTENT, intent)
        _set(props, HORIZONTAL_RESOLUTION, settings.dpi)
        _set(props, VERTICAL_RESOLUTION, settings.dpi)
        dpi_x = _get(props, HORIZONTAL_RESOLUTION, settings.dpi) or settings.dpi
        dpi_y = _get(props, VERTICAL_RESOLUTION, settings.dpi) or settings.dpi
        _set(props, HORIZONTAL_START, 0)
        _set(props, VERTICAL_START, 0)
        if settings.page in PAGE_SIZES:
            w_in, h_in = PAGE_SIZES[settings.page]
            _set(props, HORIZONTAL_EXTENT, int(w_in * dpi_x))
            _set(props, VERTICAL_EXTENT, int(h_in * dpi_y))
        else:
            for prop_id in (HORIZONTAL_EXTENT, VERTICAL_EXTENT):
                try:
                    prop = props.Item(str(prop_id))
                    prop.Value = prop.SubTypeMax
                except Exception:  # noqa: BLE001
                    pass

        count = 0
        while not is_cancelled():
            try:
                try:
                    image = item.Transfer(FORMAT_PNG)
                except pywintypes.com_error as exc:
                    if _hresult(exc) in (PAPER_EMPTY,):
                        raise
                    image = item.Transfer(FORMAT_BMP)
            except pywintypes.com_error as exc:
                code = _hresult(exc)
                if code == PAPER_EMPTY and count > 0:
                    break  # the feeder is empty: every page was scanned
                raise ScanError(ERRORS.get(code, f"Scanning failed (error {code:#x})." if code else
                                           "Scanning failed.")) from None
            count += 1
            ext = (image.FileExtension or "png").lower()
            path = folder / f"wia-{int(time.time() * 1000)}-{count}.{ext}"
            image.SaveFile(str(path))
            on_page(path)
            if not use_feeder:
                break
        return count
