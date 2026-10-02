"""SANE scanning through the scanimage command (Linux)."""

from __future__ import annotations

import re
import shutil
import subprocess

from .base import BW, COLOR, FEEDER, FLATBED, GRAY, PAGE_SIZES, ScanBackend, ScanError, ScannerInfo


class SaneBackend(ScanBackend):
    name = "SANE"

    def unavailable_reason(self):
        return None if shutil.which("scanimage") else "Install SANE (the scanimage command) to scan on Linux."

    def list_devices(self):
        if not shutil.which("scanimage"):
            return []
        out = subprocess.run(["scanimage", "-L"], capture_output=True, text=True, timeout=60).stdout
        devices = []
        for m in re.finditer(r"device `([^']+)' is a (.+)", out):
            devices.append(ScannerInfo(m.group(1), m.group(2).strip(), [FLATBED, FEEDER]))
        return devices

    def scan(self, device, settings, folder, on_page, is_cancelled):
        mode = {COLOR: "Color", GRAY: "Gray", BW: "Lineart"}[settings.color]
        cmd = ["scanimage", "-d", device.id, "--format=png", f"--resolution={settings.dpi}", f"--mode={mode}"]
        if settings.page in PAGE_SIZES:
            w, h = PAGE_SIZES[settings.page]
            cmd += ["-x", f"{w * 25.4:.0f}", "-y", f"{h * 25.4:.0f}"]
        if settings.source != FLATBED:
            cmd += ["--source=ADF Duplex" if settings.source == "duplex" else "--source=ADF",
                    f"--batch={folder}/sane-%03d.png"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            files = sorted(folder.glob("sane-*.png"))
            if not files:
                raise ScanError(proc.stderr.strip() or "No pages were scanned.")
            for f in files:
                on_page(f)
            return len(files)
        path = folder / f"sane-{len(list(folder.glob('*.png'))):03d}.png"
        with open(path, "wb") as fh:
            proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE, timeout=600)
        if proc.returncode != 0:
            raise ScanError(proc.stderr.decode(errors="replace").strip() or "Scanning failed.")
        on_page(path)
        return 1
