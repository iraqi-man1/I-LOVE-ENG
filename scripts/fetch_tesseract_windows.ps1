# Prepare vendor\tesseract with the Tesseract OCR engine for the Windows build.
# Tesseract is Apache-2.0 licensed. The Windows binaries are the UB Mannheim
# build, installed here through Chocolatey.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dest = Join-Path $root "vendor\tesseract"

$source = "C:\Program Files\Tesseract-OCR"
if (-not (Test-Path "$source\tesseract.exe")) {
    choco install tesseract -y --no-progress
}
if (-not (Test-Path "$source\tesseract.exe")) { throw "Tesseract was not installed" }

if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
New-Item -ItemType Directory -Force -Path "$dest\tessdata" | Out-Null
Copy-Item "$source\tesseract.exe" $dest
Copy-Item "$source\*.dll" $dest
foreach ($doc in @("LICENSE", "LICENSE.txt", "doc\LICENSE", "doc\AUTHORS")) {
    if (Test-Path "$source\$doc") { Copy-Item "$source\$doc" "$dest\" }
}
Copy-Item "$source\tessdata\eng.traineddata" "$dest\tessdata\"
Copy-Item "$source\tessdata\osd.traineddata" "$dest\tessdata\" -ErrorAction SilentlyContinue

# Arabic language data from the official tessdata repository (Apache-2.0).
$ara = "https://github.com/tesseract-ocr/tessdata/raw/main/ara.traineddata"
Invoke-WebRequest -Uri $ara -OutFile "$dest\tessdata\ara.traineddata" -UseBasicParsing

& "$dest\tesseract.exe" --version
& "$dest\tesseract.exe" --list-langs --tessdata-dir "$dest\tessdata"
