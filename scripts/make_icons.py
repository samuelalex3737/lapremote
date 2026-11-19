"""Draw the LapRemote logo mark and write every icon and iOS splash image the PWA needs.

    uv run --project agent python scripts/make_icons.py

The mark is original: a rounded gradient tile holding a trackpad outline with a
play triangle. Everything is drawn with Pillow at high resolution, then
downsampled, so edges stay smooth.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "public"
ICONS = OUT / "icons"
SPLASH = OUT / "splash"

TOP = (91, 108, 255)  # #5b6cff
BOTTOM = (168, 85, 247)  # #a855f7
BACKGROUND = (7, 7, 11)  # app background #07070b
WORK = 2048

# iOS launch images (portrait, device pixels) and the device-width/height/ratio they match.
SPLASHES: tuple[tuple[int, int, int, int, int], ...] = (
    (1290, 2796, 430, 932, 3),  # iPhone 15 Plus / 15 Pro Max / 14 Pro Max
    (1179, 2556, 393, 852, 3),  # iPhone 15 / 15 Pro / 14 Pro
    (1284, 2778, 428, 926, 3),  # iPhone 14 Plus / 13 Pro Max / 12 Pro Max
    (1170, 2532, 390, 844, 3),  # iPhone 14 / 13 / 12
    (1125, 2436, 375, 812, 3),  # iPhone 13 mini / 12 mini / 11 Pro / X
    (828, 1792, 414, 896, 2),  # iPhone 11 / XR
    (750, 1334, 375, 667, 2),  # iPhone SE (2nd and 3rd gen) / 8
)


def gradient(size: int) -> Image.Image:
    """Diagonal gradient from TOP (top-left) to BOTTOM (bottom-right)."""
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM, strict=True))
    return img


def mark(size: int, *, full_bleed: bool, inset: float = 0.0) -> Image.Image:
    """The logo at ``size`` px. ``full_bleed`` fills the square (for maskable icons)."""
    s = WORK
    base = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    tile = gradient(s // 8).resize((s, s), Image.Resampling.BICUBIC)
    mask = Image.new("L", (s, s), 0)
    draw_mask = ImageDraw.Draw(mask)
    if full_bleed:
        draw_mask.rectangle((0, 0, s, s), fill=255)
    else:
        draw_mask.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.225), fill=255)
    base.paste(tile, (0, 0), mask)

    draw = ImageDraw.Draw(base)
    pad = s * (0.24 + inset)
    # Trackpad outline.
    box = (pad, pad * 1.05, s - pad, s - pad * 1.05)
    draw.rounded_rectangle(
        box, radius=int(s * 0.09), outline=(255, 255, 255, 255), width=int(s * 0.045)
    )
    # Play triangle.
    cx, cy = s / 2 + s * 0.02, s / 2
    r = s * (0.13 - inset * 0.3)
    draw.polygon(
        [(cx - r * 0.8, cy - r), (cx - r * 0.8, cy + r), (cx + r * 1.05, cy)],
        fill=(255, 255, 255, 255),
    )
    return base.resize((size, size), Image.Resampling.LANCZOS)


def save(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)
    print(f"wrote {path.relative_to(ROOT)} ({img.width}x{img.height})")


def splash(width: int, height: int) -> Image.Image:
    img = Image.new("RGB", (width, height), BACKGROUND)
    logo = mark(int(min(width, height) * 0.28), full_bleed=False)
    img.paste(logo, ((width - logo.width) // 2, (height - logo.height) // 2), logo)
    return img


def main() -> int:
    save(mark(192, full_bleed=False), ICONS / "icon-192.png")
    save(mark(512, full_bleed=False), ICONS / "icon-512.png")
    # Maskable icons keep the mark inside the central 80% safe zone.
    save(mark(512, full_bleed=True, inset=0.08), ICONS / "maskable-512.png")
    apple = Image.new("RGB", (180, 180), BACKGROUND)
    apple_mark = mark(180, full_bleed=True, inset=0.04)
    apple.paste(apple_mark, (0, 0), apple_mark)
    save(apple, ICONS / "apple-touch-icon.png")
    save(mark(32, full_bleed=False), ICONS / "favicon-32.png")
    for width, height, _w, _h, _ratio in SPLASHES:
        save(splash(width, height), SPLASH / f"splash-{width}x{height}.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
