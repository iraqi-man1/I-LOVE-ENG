import hashlib
import io
import json

import pytest

from pdftoolbox.updater import github


def asset(name, size=10):
    return {"name": name, "browser_download_url": f"https://example.invalid/{name}", "size": size}


ASSETS = [asset("PDFToolbox-1.2.0-windows-x64-setup.exe"), asset("PDFToolbox-1.2.0-macos-arm64.dmg"),
          asset("PDFToolbox-1.2.0-macos-x64.dmg"), asset("SHA256SUMS.txt")]


def test_pick_asset():
    assert github.pick_asset(ASSETS, "windows", "x64")["name"].endswith("setup.exe")
    assert github.pick_asset(ASSETS, "macos", "arm64")["name"].endswith("arm64.dmg")
    assert github.pick_asset(ASSETS, "macos", "x64")["name"].endswith("x64.dmg")
    assert github.pick_asset([asset("a.zip")], "windows", "x64") is None


class FakeResponse(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_check_and_download(monkeypatch, tmp_path):
    payload = b"installer bytes" * 1000
    digest = hashlib.sha256(payload).hexdigest()
    name = "PDFToolbox-9.0.0-windows-x64-setup.exe"
    release = {"tag_name": "v9.0.0", "name": "9.0.0", "body": "Notes", "html_url": "https://x",
               "assets": [asset(name, len(payload)), asset("SHA256SUMS.txt"),
                          asset("PDFToolbox-9.0.0-macos-arm64.dmg", len(payload)),
                          asset("PDFToolbox-9.0.0-macos-x64.dmg", len(payload))]}

    def fake_open(url, timeout, accept=None):
        if url.startswith("https://api.github.com"):
            return FakeResponse(json.dumps(release).encode())
        if url.endswith("SHA256SUMS.txt"):
            return FakeResponse(f"{digest}  {name}\n{digest}  PDFToolbox-9.0.0-macos-arm64.dmg\n"
                                f"{digest}  PDFToolbox-9.0.0-macos-x64.dmg\n".encode())
        return FakeResponse(payload, {"Content-Length": str(len(payload))})

    monkeypatch.setattr(github, "_open", fake_open)
    monkeypatch.setattr(github, "platform_key", lambda: ("windows", "x64"))
    assert github.check_latest("9.0.0") is None
    found = github.check_latest("1.0.0")
    assert found and found.version == "9.0.0" and found.asset_name == name
    path = github.download(found, tmp_path)
    assert path.read_bytes() == payload

    # A corrupted download is rejected.
    payload_bad = b"tampered"
    monkeypatch.setattr(github, "_open", lambda url, timeout, accept=None: (
        fake_open(url, timeout) if not url.endswith(".exe") else FakeResponse(payload_bad)))
    found.asset_size = 0
    with pytest.raises(github.UpdateError):
        github.download(found, tmp_path / "again")


def test_offline(monkeypatch):
    import urllib.error

    def boom(*a, **k):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(github, "_open", boom)
    with pytest.raises(github.UpdateError):
        github.check_latest("1.0.0")
