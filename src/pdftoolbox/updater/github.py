"""Check GitHub releases for a newer version and download it safely."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from packaging.version import InvalidVersion, Version

from pdftoolbox import APP_NAME, GITHUB_REPO, __version__

API = "https://api.github.com/repos/{repo}/releases/latest"
CHECKSUM_NAMES = ("SHA256SUMS.txt", "SHA256SUMS", "checksums.txt")


class UpdateError(Exception):
    pass


@dataclass
class Release:
    version: str
    tag: str
    name: str
    notes: str
    page_url: str
    asset_name: str
    asset_url: str
    asset_size: int
    checksum_url: str | None


def _ssl_context() -> ssl.SSLContext:
    # Use the operating system's certificate store (works behind corporate proxies).
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # noqa: BLE001
        context = ssl.create_default_context()
        try:
            import certifi

            context.load_verify_locations(certifi.where())
        except Exception:  # noqa: BLE001
            pass
        return context


def _open(url: str, timeout: float, accept: str = "application/vnd.github+json"):
    request = urllib.request.Request(url, headers={
        "Accept": accept,
        "User-Agent": f"{APP_NAME.replace(' ', '')}/{__version__}",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return urllib.request.urlopen(request, timeout=timeout, context=_ssl_context())


def parse_version(text: str) -> Version | None:
    text = text.strip().lstrip("vV")
    try:
        return Version(text)
    except InvalidVersion:
        return None


def platform_key() -> tuple[str, str]:
    system = "windows" if sys.platform.startswith("win") else "macos" if sys.platform == "darwin" else "linux"
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    return system, arch


def pick_asset(assets: list[dict], system: str, arch: str) -> dict | None:
    """Choose the installer for this computer from a release's files."""
    def name(a):
        return a.get("name", "").lower()

    if system == "windows":
        candidates = [a for a in assets if name(a).endswith(".exe") and "windows" in name(a)]
        candidates = candidates or [a for a in assets if name(a).endswith(".exe")]
        return next((a for a in candidates if arch in name(a)), candidates[0] if candidates else None)
    if system == "macos":
        candidates = [a for a in assets if name(a).endswith(".dmg")]
        exact = [a for a in candidates if arch in name(a) or (arch == "x64" and ("x86_64" in name(a) or "intel" in name(a)))]
        universal = [a for a in candidates if "universal" in name(a)]
        return (exact or universal or [None])[0]
    candidates = [a for a in assets if name(a).endswith((".appimage", ".tar.gz"))]
    return candidates[0] if candidates else None


def check_latest(current: str = __version__, repo: str = GITHUB_REPO, timeout: float = 10.0) -> Release | None:
    """Return the newest release if it is newer than ``current``, else None.

    Raises UpdateError when GitHub cannot be reached (for example offline).
    """
    try:
        with _open(API.format(repo=repo), timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None  # no published releases yet
        raise UpdateError(f"GitHub returned an error ({exc.code}).") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise UpdateError(f"Could not reach GitHub ({exc}).") from None
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name") or ""
    latest, mine = parse_version(tag), parse_version(current)
    if latest is None or mine is None or latest <= mine:
        return None
    assets = data.get("assets") or []
    asset = pick_asset(assets, *platform_key())
    checksum = next((a for a in assets if a.get("name") in CHECKSUM_NAMES), None)
    return Release(
        version=str(latest),
        tag=tag,
        name=data.get("name") or tag,
        notes=(data.get("body") or "").strip(),
        page_url=data.get("html_url") or f"https://github.com/{repo}/releases",
        asset_name=asset["name"] if asset else "",
        asset_url=asset["browser_download_url"] if asset else "",
        asset_size=int(asset.get("size", 0)) if asset else 0,
        checksum_url=checksum["browser_download_url"] if checksum else None,
    )


def expected_checksum(release: Release, timeout: float = 20.0) -> str | None:
    if not release.checksum_url:
        return None
    try:
        with _open(release.checksum_url, timeout, accept="application/octet-stream") as response:
            text = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError(f"Could not download the checksum file ({exc}).") from None
    for line in text.splitlines():
        m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+)$", line.strip())
        if m and m.group(2).strip() == release.asset_name:
            return m.group(1).lower()
    return None


def download(release: Release, folder: Path, progress: Callable[[int, int], None] | None = None,
             is_cancelled: Callable[[], bool] | None = None) -> Path:
    """Download the installer and verify its SHA-256 checksum."""
    if not release.asset_url:
        raise UpdateError("This release has no installer for your computer.")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / release.asset_name
    part = target.with_name(target.name + ".part")
    expected = expected_checksum(release)
    digest = hashlib.sha256()
    try:
        with _open(release.asset_url, 60, accept="application/octet-stream") as response, open(part, "wb") as fh:
            total = int(response.headers.get("Content-Length") or release.asset_size or 0)
            received = 0
            while True:
                if is_cancelled and is_cancelled():
                    raise UpdateError("Download cancelled.")
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if progress:
                    progress(received, total)
    except (urllib.error.URLError, OSError) as exc:
        part.unlink(missing_ok=True)
        raise UpdateError(f"The download failed ({exc}).") from None
    except UpdateError:
        part.unlink(missing_ok=True)
        raise
    if release.asset_size and part.stat().st_size != release.asset_size:
        part.unlink(missing_ok=True)
        raise UpdateError("The download was incomplete. Please try again.")
    if expected and digest.hexdigest() != expected:
        part.unlink(missing_ok=True)
        raise UpdateError("The downloaded file failed its integrity check and was deleted.")
    part.replace(target)
    return target
