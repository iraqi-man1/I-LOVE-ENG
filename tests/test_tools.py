import shutil
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium
import pytest
from PIL import Image

from pdftoolbox.core.errors import ToolError
from pdftoolbox.core.pages import parse_groups, parse_pages
from pdftoolbox.tools import all_tools


def page_count(path):
    with pikepdf.open(path) as pdf:
        return len(pdf.pages)


def page_text(path, index=0, password=None):
    doc = pdfium.PdfDocument(str(path), password=password)
    try:
        return doc[index].get_textpage().get_text_range()
    finally:
        doc.close()


def test_registry_has_every_tool():
    ids = {t.id for t in all_tools()}
    expected = {"merge", "split", "extract_pages", "delete_pages", "organize", "rotate", "crop", "compress",
                "pdf_to_image", "image_to_pdf", "extract_images", "word_to_pdf", "excel_to_pdf",
                "powerpoint_to_pdf", "watermark", "page_numbers", "header_footer", "protect", "unlock",
                "metadata", "info", "grayscale", "optimize", "repair", "ocr", "batch"}
    assert expected <= ids


def test_parse_pages():
    assert parse_pages("", 5) == [0, 1, 2, 3, 4]
    assert parse_pages("1-3, 5", 5) == [0, 1, 2, 4]
    assert parse_pages("4-", 5) == [3, 4]
    assert parse_pages("-2", 5) == [0, 1]
    assert parse_pages("last", 5) == [4]
    assert parse_pages("odd", 5) == [0, 2, 4]
    assert parse_pages("even", 5) == [1, 3]
    assert parse_pages("3-1", 5) == [2, 1, 0]
    assert parse_groups("1-2; 3,5", 5) == [[0, 1], [2, 4]]
    assert parse_groups("1-2, 3-5", 5) == [[0, 1], [2, 3, 4]]
    with pytest.raises(ToolError):
        parse_pages("7", 5)
    with pytest.raises(ToolError):
        parse_pages("abc", 5)


def test_merge(make_pdf, run_tool, tmp_path):
    a, b = make_pdf(pages=2), make_pdf(pages=3)
    out = tmp_path / "merged.pdf"
    [r] = run_tool("merge", [a, b], output_file=out)
    assert r.outputs == [str(out)]
    assert page_count(out) == 5
    with pikepdf.open(out) as pdf, pdf.open_outline() as outline:
        assert [i.title for i in outline.root] == [a.stem, b.stem]


def test_split_modes(make_pdf, run_tool):
    src = make_pdf(pages=5)
    [r] = run_tool("split", [src], {"mode": "each"})
    assert len(r.outputs) == 5
    [r] = run_tool("split", [src], {"mode": "every", "every": 2})
    assert [page_count(p) for p in r.outputs] == [2, 2, 1]
    [r] = run_tool("split", [src], {"mode": "ranges", "ranges": "1-2, 3-5"})
    assert [page_count(p) for p in r.outputs] == [2, 3]
    [r] = run_tool("split", [src], {"mode": "parts", "parts": 2})
    assert [page_count(p) for p in r.outputs] == [3, 2]


def test_split_by_bookmarks(make_pdf, run_tool, tmp_path):
    a, b = make_pdf(pages=2), make_pdf(pages=3)
    merged = tmp_path / "m.pdf"
    run_tool("merge", [a, b], output_file=merged)
    [r] = run_tool("split", [merged], {"mode": "bookmarks"})
    assert [page_count(p) for p in r.outputs] == [2, 3]


def test_extract_delete_rotate(make_pdf, run_tool):
    src = make_pdf(pages=4)
    [r] = run_tool("extract_pages", [src], {"pages": "4, 1"})
    assert page_count(r.outputs[0]) == 2
    assert "Hello page 4" in page_text(r.outputs[0], 0)
    [r] = run_tool("delete_pages", [src], {"pages": "2-3"})
    assert page_count(r.outputs[0]) == 2
    [r] = run_tool("delete_pages", [src], {"pages": "1-4"}, expect_error=True)
    assert r.error
    [r] = run_tool("rotate", [src], {"angle": 90, "pages": "1"})
    with pikepdf.open(r.outputs[0]) as pdf:
        assert pdf.pages[0].obj.Rotate == 90
        assert int(pdf.pages[1].obj.get("/Rotate", 0)) == 0


def test_organize(make_pdf, run_tool):
    src = make_pdf(pages=3)
    layout = [{"page": 2, "rotate": 90}, {"page": 0, "rotate": 0}]
    [r] = run_tool("organize", [src], {"method": "visual", "layout": layout})
    assert page_count(r.outputs[0]) == 2
    assert "Hello page 3" in page_text(r.outputs[0], 0)
    [r] = run_tool("organize", [src], {"method": "reverse"})
    assert "Hello page 3" in page_text(r.outputs[0], 0)
    [r] = run_tool("organize", [src], {"method": "order", "order": "2"})
    assert page_count(r.outputs[0]) == 3
    assert "Hello page 2" in page_text(r.outputs[0], 0)


def test_crop(make_pdf, run_tool):
    src = make_pdf(pages=1)
    [r] = run_tool("crop", [src], {"mode": "margins", "unit": "pt", "top": 10, "bottom": 20, "left": 30, "right": 40})
    with pikepdf.open(r.outputs[0]) as pdf:
        assert [float(v) for v in pdf.pages[0].obj.CropBox] == [30, 20, 555, 832]
    [r] = run_tool("crop", [src], {"mode": "auto", "padding": 0})
    with pikepdf.open(r.outputs[0]) as pdf:
        x0, y0, x1, y1 = (float(v) for v in pdf.pages[0].obj.CropBox)
        assert x0 > 30 and y1 < 800 and (x1 - x0) < 595


def test_crop_rotated_page(make_pdf, run_tool):
    src = make_pdf(pages=1, rotate=90)
    # Visible top margin on a page rotated 90° is the left side of the media box.
    [r] = run_tool("crop", [src], {"mode": "margins", "unit": "pt", "top": 50, "bottom": 0, "left": 0, "right": 0})
    with pikepdf.open(r.outputs[0]) as pdf:
        assert [float(v) for v in pdf.pages[0].obj.CropBox] == [50, 0, 595, 842]


def test_pdf_to_image_and_back(make_pdf, run_tool, tmp_path):
    src = make_pdf(pages=2)
    [r] = run_tool("pdf_to_image", [src], {"format": "png", "dpi": 72})
    assert len(r.outputs) == 2
    with Image.open(r.outputs[0]) as im:
        assert im.size == (595, 842)
    [r] = run_tool("pdf_to_image", [src], {"format": "jpg", "dpi": 72, "pages": "2"})
    assert len(r.outputs) == 1 and r.outputs[0].endswith(".jpg")
    jpg = Path(r.outputs[0])
    png = tmp_path / "alpha.png"
    Image.new("RGBA", (200, 100), (255, 0, 0, 128)).save(png)
    out = tmp_path / "images.pdf"
    [r] = run_tool("image_to_pdf", [jpg, png], {"page_size": "a4"}, output_file=out)
    assert page_count(out) == 2
    with pikepdf.open(out) as pdf:
        images = list(pdf.pages[0].get_images().values())
        assert images[0].Filter == "/DCTDecode"  # embedded without re-encoding
        assert "/SMask" in list(pdf.pages[1].get_images().values())[0]


def test_extract_images(make_pdf, run_tool):
    src = make_pdf(pages=1, image=True)
    [r] = run_tool("extract_images", [src], {"format": "png"})
    assert len(r.outputs) == 1
    with Image.open(r.outputs[0]) as im:
        assert im.size == (400, 300)


@pytest.mark.parametrize("rotate", [0, 90, 270])
def test_watermark_page_numbers_header(make_pdf, run_tool, rotate):
    src = make_pdf(pages=3, rotate=rotate)
    [r] = run_tool("watermark", [src], {"text": "DRAFT مسودة"})
    assert "DRAFT" in page_text(r.outputs[0], 1)
    [r] = run_tool("page_numbers", [src], {"format": "Page {n} of {total}", "skip": 1})
    assert "Page 1 of 2" in page_text(r.outputs[0], 1)
    assert "Page" not in page_text(r.outputs[0], 0)
    [r] = run_tool("header_footer", [src], {"header_center": "Report {page}/{total}", "footer_right": "",
                                            "footer_left": ""})
    assert "Report 2/3" in page_text(r.outputs[0], 1)


def test_watermark_position_on_rotated_page(make_pdf, run_tool):
    """A top-left stamp must appear at the top left of the page as displayed."""
    src = make_pdf(pages=1, rotate=90)
    [r] = run_tool("page_numbers", [src], {"position": "top-left", "format": "{n}", "size": 40, "margin": 5})
    doc = pdfium.PdfDocument(r.outputs[0])
    page = doc[0]
    w, h = page.get_size()
    text = page.get_textpage()
    boxes = [text.get_charbox(i) for i in range(text.count_chars()) if text.get_text_range(i, 1) == "1"]
    assert boxes
    # pdfium char boxes are in page space; render to find where the digit is drawn instead.
    image = page.render(scale=1).to_pil().convert("L")
    dark = [(x, y) for x in range(0, image.width, 2) for y in range(0, image.height // 4, 2)
            if image.getpixel((x, y)) < 100 and x < image.width // 4]
    assert dark, "page number not found in the displayed top-left corner"


def test_protect_and_unlock(make_pdf, run_tool):
    src = make_pdf(pages=1)
    [r] = run_tool("protect", [src], {"password": "s3cret", "copy": False})
    protected = r.outputs[0]
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(protected)
    with pikepdf.open(protected, password="s3cret") as pdf:
        assert pdf.is_encrypted
    [r] = run_tool("unlock", [protected], {"password": "wrong"}, expect_error=True)
    assert r.error
    [r] = run_tool("unlock", [protected], {"password": "s3cret"})
    with pikepdf.open(r.outputs[0]) as pdf:
        assert not pdf.is_encrypted


def test_edit_keeps_protection(make_pdf, run_tool):
    src = make_pdf(pages=2)
    [r] = run_tool("protect", [src], {"password": "pw"})
    [r] = run_tool("rotate", [r.outputs[0]], passwords={r.outputs[0]: "pw"})
    with pikepdf.open(r.outputs[0], password="pw") as pdf:
        assert pdf.is_encrypted


def test_metadata_and_info(make_pdf, run_tool):
    src = make_pdf(pages=2)
    [r] = run_tool("metadata", [src], {"title": "My title", "author": "Ali; Sara", "keywords": "a, b"})
    with pikepdf.open(r.outputs[0]) as pdf:
        assert str(pdf.docinfo.Title) == "My title"
        assert str(pdf.docinfo.Author) == "Ali; Sara"
        meta = pdf.open_metadata()
        assert meta["dc:title"] == "My title"
    [r] = run_tool("info", [r.outputs[0]])
    assert "Pages: 2" in r.report
    assert "A4 portrait (2)" in r.report
    assert "Title: My title" in r.report


def test_grayscale(make_pdf, run_tool):
    src = make_pdf(pages=1, image=True)
    for method in ("preserve", "rasterize"):
        [r] = run_tool("grayscale", [src], {"method": method})
        doc = pdfium.PdfDocument(r.outputs[0])
        image = doc[0].render(scale=0.5).to_pil().convert("RGB")
        pixels = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
        colourful = sum(1 for px in pixels if max(px) - min(px) > 30)
        assert colourful == 0, f"{method}: {colourful} coloured pixels left"
        if method == "preserve":
            assert "Hello page 1" in page_text(r.outputs[0])


def test_compress_and_optimize(make_pdf, run_tool, tmp_path):
    big = tmp_path / "big.png"
    # A noisy photo-like image compresses badly losslessly.
    import random

    random.seed(1)
    im = Image.effect_noise((1600, 1200), 60).convert("RGB")
    im.save(big)
    pdf_path = tmp_path / "photo.pdf"
    run_tool("image_to_pdf", [big], {"page_size": "a4"}, output_file=pdf_path)
    [r] = run_tool("compress", [pdf_path], {"level": "high"})
    assert Path(r.outputs[0]).stat().st_size < pdf_path.stat().st_size / 2
    assert "smaller" in (r.message or "")
    [r] = run_tool("optimize", [pdf_path])
    assert page_count(r.outputs[0]) == 1


def test_repair(make_pdf, run_tool, tmp_path):
    src = make_pdf(pages=3)
    data = bytearray(src.read_bytes())
    # Destroy the cross-reference table offset.
    idx = data.rfind(b"startxref")
    data[idx + 10: idx + 16] = b"999999"
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(bytes(data))
    [r] = run_tool("repair", [broken])
    assert page_count(r.outputs[0]) == 3


def test_batch_pipeline(make_pdf, run_tool):
    files = [make_pdf(pages=2), make_pdf(pages=3)]
    steps = [
        {"tool": "rotate", "options": {"angle": 180}},
        {"tool": "page_numbers", "options": {}},
        {"tool": "protect", "options": {"password": "x"}},
        {"tool": "compress", "options": {"level": "low"}},
    ]
    results = run_tool("batch", files, {"steps": steps})
    assert len(results) == 2
    for r, n in zip(results, (2, 3)):
        with pikepdf.open(r.outputs[0], password="x") as pdf:
            assert len(pdf.pages) == n
            assert pdf.pages[0].obj.Rotate == 180


def test_batch_continues_after_error(make_pdf, run_tool, tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf at all")
    good = make_pdf(pages=1)
    results = run_tool("rotate", [bad, good], expect_error=True)
    assert results[0].error and not results[1].error


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract is not installed")
def test_ocr(tmp_path, run_tool):
    # Build a scanned-looking PDF: an image of text with no text layer.
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter

    from pdftoolbox.core import stamp

    stamp.ensure_qt()
    img = QImage(1240, 1754, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    f = QFont()
    f.setPixelSize(64)
    p.setFont(f)
    p.setPen(QColor("black"))
    p.drawText(QRectF(100, 200, 1100, 200), int(Qt.AlignmentFlag.AlignLeft), "Invoice number 12345")
    p.end()
    png = tmp_path / "scan.png"
    img.save(str(png))
    with Image.open(png) as im:
        im.save(png, dpi=(150, 150))
    scanned = tmp_path / "scan.pdf"
    run_tool("image_to_pdf", [png], {"page_size": "fit"}, output_file=scanned)
    assert page_text(scanned).strip() == ""
    [r] = run_tool("ocr", [scanned], {"languages": ["eng"], "text_file": True})
    assert "12345" in page_text(r.outputs[0])
    assert any(o.endswith(".txt") for o in r.outputs)
