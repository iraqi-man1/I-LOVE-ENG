#!/bin/bash
# Package dist/PDF Toolbox.app into a compressed disk image.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$1"
ARCH="$2"
APP="$ROOT/dist/PDF Toolbox.app"
STAGE="$ROOT/build/dmg"
OUT="$ROOT/dist/PDFToolbox-$VERSION-macos-$ARCH.dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
ditto "$APP" "$STAGE/PDF Toolbox.app"
ln -s /Applications "$STAGE/Applications"
rm -f "$OUT"
hdiutil create -volname "PDF Toolbox" -srcfolder "$STAGE" -ov -format UDZO -fs HFS+ "$OUT"
echo "$OUT"
