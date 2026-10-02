"""Start the downloaded installer, then let the app quit so it can be replaced."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from .github import UpdateError


def current_app_bundle() -> Path | None:
    """The running .app bundle on macOS (only when frozen)."""
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return None
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    return None


def install_windows(installer: Path) -> None:
    # Inno Setup: install silently, close this app, and start the new version.
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(installer), "/SILENT", "/SP-", "/NOCANCEL", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELAUNCH"],
                     creationflags=flags, close_fds=True)


def install_macos(dmg: Path) -> bool:
    """Replace the running app with the one inside ``dmg``.

    Returns False when the app cannot be replaced automatically (for example
    it lives in a folder the user cannot write to); the disk image is then
    opened in Finder so the user can drag the new version into Applications.
    """
    bundle = current_app_bundle()
    if bundle is None or not os.access(bundle.parent, os.W_OK):
        subprocess.Popen(["open", str(dmg)])
        return False
    mount = Path(tempfile.mkdtemp(prefix="pdftoolbox-update-"))
    attach = subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", str(mount),
                             str(dmg)], capture_output=True, text=True)
    if attach.returncode != 0:
        raise UpdateError("The update could not be opened: " + attach.stderr.strip())
    apps = list(mount.glob("*.app"))
    if not apps:
        subprocess.run(["hdiutil", "detach", str(mount), "-force"], capture_output=True)
        raise UpdateError("The update does not contain an application.")
    new_app = apps[0]
    staging = bundle.parent / f".{bundle.stem}-update.app"
    copy = subprocess.run(["ditto", str(new_app), str(staging)], capture_output=True, text=True)
    subprocess.run(["hdiutil", "detach", str(mount), "-force"], capture_output=True)
    if copy.returncode != 0:
        subprocess.run(["rm", "-rf", str(staging)])
        raise UpdateError("The update could not be copied: " + copy.stderr.strip())
    subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(staging)], capture_output=True)
    q = shlex.quote
    script = f"""#!/bin/sh
while kill -0 {os.getpid()} 2>/dev/null; do sleep 0.3; done
old={q(str(bundle))}.old
rm -rf "$old"
mv {q(str(bundle))} "$old" && mv {q(str(staging))} {q(str(bundle))} && rm -rf "$old"
if [ ! -d {q(str(bundle))} ]; then mv "$old" {q(str(bundle))}; fi
open {q(str(bundle))}
rm -f "$0"
"""
    script_path = Path(tempfile.gettempdir()) / f"pdftoolbox-update-{os.getpid()}.sh"
    script_path.write_text(script)
    script_path.chmod(0o755)
    subprocess.Popen(["/bin/sh", str(script_path)], start_new_session=True, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    return True


def install(path: Path) -> bool:
    """Launch the update. True means the app should quit now."""
    if sys.platform.startswith("win"):
        install_windows(path)
        return True
    if sys.platform == "darwin":
        return install_macos(path)
    subprocess.Popen(["xdg-open", str(path.parent)])
    return False
