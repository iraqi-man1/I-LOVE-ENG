# PyInstaller build description. Run from the repository root:
#   pyinstaller --noconfirm packaging/pdftoolbox.spec
# Produces dist/PDF Toolbox/ (Windows) or dist/PDF Toolbox.app (macOS).
import os
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
VERSION = re.search(r'__version__ = "([^"]+)"', (SRC / "pdftoolbox" / "__init__.py").read_text()).group(1)
APP_NAME = "PDF Toolbox"
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")

datas = [
    (str(SRC / "pdftoolbox" / "resources"), "pdftoolbox/resources"),
]
tesseract = ROOT / "vendor" / "tesseract"
if tesseract.is_dir():
    # Bundled as plain files so its own libraries stay exactly as prepared.
    datas.append((str(tesseract), "tesseract"))

hiddenimports = collect_submodules("pdftoolbox")
if IS_WIN:
    hiddenimports += ["win32com", "win32com.client", "pythoncom", "pywintypes"]
if IS_MAC:
    hiddenimports += ["ImageCaptureCore", "Foundation", "objc", "PyObjCTools.AppHelper"]

excludes = ["tkinter", "unittest", "pydoc_data", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore",
            "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtOpenGL", "PySide6.QtSql", "PySide6.QtTest",
            "PySide6.QtDesigner", "PySide6.QtHelp"]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(SRC)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,
    icon=str(ROOT / "packaging" / ("macos/app.icns" if IS_MAC else "windows/app.ico")),
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(ROOT / "build" / "version_info.txt") if IS_WIN and (ROOT / "build" / "version_info.txt").exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=APP_NAME)

if IS_MAC:
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(ROOT / "packaging" / "macos" / "app.icns"),
        bundle_identifier="com.iraqiman1.pdftoolbox",
        version=VERSION,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": os.environ.get("MACOS_MIN_VERSION", "12.0"),
            "LSApplicationCategoryType": "public.app-category.productivity",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "PDF document",
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Alternate",
                "LSItemContentTypes": ["com.adobe.pdf"],
            }],
        },
    )
