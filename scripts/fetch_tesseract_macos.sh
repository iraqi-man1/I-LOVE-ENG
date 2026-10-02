#!/bin/bash
# Prepare vendor/tesseract with a self-contained Tesseract OCR engine for the
# macOS build: the Homebrew binary plus its libraries, relinked to load from
# the app bundle. Tesseract (Apache-2.0) and its libraries use permissive
# licenses (Leptonica BSD-2, libpng, libjpeg-turbo, libtiff, libwebp, ...).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/vendor/tesseract"

brew list tesseract >/dev/null 2>&1 || brew install tesseract
brew list dylibbundler >/dev/null 2>&1 || brew install dylibbundler
PREFIX="$(brew --prefix)"
TESS="$(brew --prefix tesseract)"

rm -rf "$DEST"
mkdir -p "$DEST/lib" "$DEST/tessdata"
cp "$TESS/bin/tesseract" "$DEST/tesseract"
chmod u+w "$DEST/tesseract"
dylibbundler -od -b -x "$DEST/tesseract" -d "$DEST/lib" -p @executable_path/lib/ -s "$PREFIX/lib" -cd </dev/null
# Re-sign everything we modified (required on Apple silicon).
for f in "$DEST/lib/"*.dylib "$DEST/tesseract"; do
  codesign --force --sign - "$f"
done
cp "$TESS/share/tessdata/eng.traineddata" "$DEST/tessdata/"
cp "$TESS/share/tessdata/osd.traineddata" "$DEST/tessdata/" || true
curl -fsSL -o "$DEST/tessdata/ara.traineddata" https://github.com/tesseract-ocr/tessdata/raw/main/ara.traineddata
cp "$TESS/LICENSE" "$DEST/LICENSE" 2>/dev/null || true

# Make sure it runs without Homebrew's folders.
env -i PATH=/usr/bin:/bin "$DEST/tesseract" --version
"$DEST/tesseract" --list-langs --tessdata-dir "$DEST/tessdata"
if otool -L "$DEST/tesseract" "$DEST/lib/"*.dylib | grep -E "$PREFIX|/usr/local/(opt|Cellar)"; then
  echo "Some libraries still point at Homebrew" >&2
  exit 1
fi
