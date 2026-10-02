"""Write build/version_info.txt (Windows file properties) from the app version."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
version = re.search(r'__version__ = "([^"]+)"', (ROOT / "src" / "pdftoolbox" / "__init__.py").read_text()).group(1)
parts = [int(p) for p in re.findall(r"\d+", version)[:3]] + [0]
while len(parts) < 4:
    parts.insert(-1, 0)
t = tuple(parts[:4])
text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                    date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'PDF Toolbox'),
      StringStruct('FileDescription', 'PDF Toolbox'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'PDF Toolbox'),
      StringStruct('OriginalFilename', 'PDF Toolbox.exe'),
      StringStruct('ProductName', 'PDF Toolbox'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
(ROOT / "build").mkdir(exist_ok=True)
(ROOT / "build" / "version_info.txt").write_text(text, encoding="utf-8")
print(version)
