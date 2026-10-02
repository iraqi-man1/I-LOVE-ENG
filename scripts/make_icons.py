"""Generate the application icon in PNG, ICO (Windows) and ICNS (macOS) formats."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def draw(size: int = 1024) -> Image.Image:
    scale = 4  # draw large, then downsample for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = int(s * 0.08)
    # Background: rounded square with a vertical gradient.
    grad = Image.new("RGBA", (s, s))
    top, bottom = (255, 112, 82), (214, 58, 44)
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / (s - 1)
        gd.line([(0, y), (s, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([pad, pad, s - pad, s - pad], radius=int(s * 0.2), fill=255)
    img.paste(grad, (0, 0), mask)
    # White page with a folded corner.
    left, right = int(s * 0.28), int(s * 0.72)
    top_y, bottom_y = int(s * 0.2), int(s * 0.8)
    fold = int(s * 0.12)
    d.polygon([(left, top_y), (right - fold, top_y), (right, top_y + fold), (right, bottom_y), (left, bottom_y)],
              fill=(255, 255, 255, 255))
    d.polygon([(right - fold, top_y), (right - fold, top_y + fold), (right, top_y + fold)], fill=(255, 205, 195, 255))
    # Text lines and a "PDF" label.
    lw = int(s * 0.025)
    for i, width in enumerate((0.32, 0.26, 0.3)):
        y = int(s * (0.36 + i * 0.07))
        d.rounded_rectangle([left + int(s * 0.06), y, left + int(s * 0.06) + int(s * width), y + lw], radius=lw // 2,
                            fill=(229, 83, 61, 140))
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(s * 0.12))
    except OSError:
        font = ImageFont.load_default()
    text = "PDF"
    box = d.textbbox((0, 0), text, font=font)
    tx = (left + right) // 2 - (box[2] - box[0]) // 2
    ty = int(s * 0.6)
    d.text((tx, ty), text, font=font, fill=(229, 83, 61, 255))
    return img.resize((size, size), Image.Resampling.LANCZOS)


def main():
    icon = draw(1024)
    res = ROOT / "src" / "pdftoolbox" / "resources" / "icons"
    res.mkdir(parents=True, exist_ok=True)
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(res / "app.png")
    (ROOT / "packaging" / "windows").mkdir(parents=True, exist_ok=True)
    icon.save(ROOT / "packaging" / "windows" / "app.ico",
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    (ROOT / "packaging" / "macos").mkdir(parents=True, exist_ok=True)
    icon.save(ROOT / "packaging" / "macos" / "app.icns")
    print("icons written")


if __name__ == "__main__":
    main()
