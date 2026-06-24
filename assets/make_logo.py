"""Render the project logo from code so it can be regenerated at any size.

Outputs into assets/:
    icon.ico     multi-size Windows icon (used by the build)
    icon.png     256px badge, for the app window
    logo.png     horizontal lockup with wordmark, for the README

Everything is drawn at 4x and downsampled, so edges stay crisp at icon
sizes. Run: python assets/make_logo.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parent

TOP = (167, 139, 250)     # #a78bfa
BOTTOM = (105, 38, 214)   # #6926d6
ACCENT = (139, 92, 246)   # #8b5cf6
ACCENT_LT = (167, 139, 250)
WHITE = (255, 255, 255)
SPARK = (237, 233, 254)   # #ede9fe


def _gradient(size: int) -> Image.Image:
    """Diagonal purple wash, lighter top-left to deeper bottom-right."""
    t = np.linspace(0, 1, size)
    gx, gy = np.meshgrid(t, t)
    blend = (gx * 0.45 + gy * 0.55)[..., None]
    arr = (np.array(TOP) * (1 - blend) + np.array(BOTTOM) * blend).astype(np.uint8)
    return Image.fromarray(arr, "RGB").convert("RGBA")


def _squircle_mask(size: int, n: float = 5.0) -> Image.Image:
    """Apple-style superellipse mask. Softer shoulders than a plain
    rounded rectangle, which is what reads as a 'real' app icon."""
    lin = np.linspace(-1, 1, size)
    x, y = np.meshgrid(lin, lin)
    inside = (np.abs(x) ** n + np.abs(y) ** n) <= 1.0
    return Image.fromarray((inside * 255).astype(np.uint8), "L")


def _sheen(size: int, mask: Image.Image) -> Image.Image:
    """A faint top-down highlight clipped to the badge, for depth."""
    ys = np.linspace(0, 1, size)[:, None]
    fall = np.clip(1 - ys / 0.55, 0, 1) ** 1.6
    alpha = Image.fromarray(np.broadcast_to((fall * 60).astype(np.uint8),
                                            (size, size)).copy(), "L")
    layer = Image.new("RGBA", (size, size), WHITE + (0,))
    layer.putalpha(ImageChops.multiply(alpha, mask))
    return layer


def badge(size: int = 1024) -> Image.Image:
    """The square app mark, no wordmark."""
    mask = _squircle_mask(size)
    img = _gradient(size)
    img.putalpha(mask)
    img.alpha_composite(_sheen(size, mask))

    d = ImageDraw.Draw(img)

    def px(fx, fy):
        return (fx * size, fy * size)

    # bold play triangle, the hero of the mark, filling the upper area
    tri = [px(0.29, 0.24), px(0.29, 0.66), px(0.63, 0.45)]
    d.polygon(tri, fill=WHITE)
    # a thick rounded stroke softens the three points
    d.line(tri + [tri[0]], fill=WHITE, width=int(size * 0.06), joint="curve")

    # ascending bars, kept fully clear of the triangle above them
    bar_w = size * 0.055
    for fx, fh, alpha in [
        (0.32, 0.08, 165), (0.42, 0.13, 210), (0.52, 0.18, 248),
    ]:
        x0, y1 = fx * size, 0.79 * size
        y0 = y1 - fh * size
        bar = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(bar).rounded_rectangle(
            [x0, y0, x0 + bar_w, y1], radius=bar_w * 0.45,
            fill=WHITE + (alpha,))
        img.alpha_composite(bar)

    # four-point sparkle with a thin waist, set above the triangle tip
    cx, cy = 0.73 * size, 0.27 * size
    a, b = size * 0.062, size * 0.013
    star = [(cx, cy - a), (cx + b, cy - b), (cx + a, cy),
            (cx + b, cy + b), (cx, cy + a), (cx - b, cy + b),
            (cx - a, cy), (cx - b, cy - b)]
    ImageDraw.Draw(img).polygon(star, fill=SPARK)
    return img


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("segoeuib.ttf", "seguisb.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def lockup() -> Image.Image:
    """Badge + 'Video Enhancer' wordmark on a transparent strip."""
    b = 220
    pad = 36
    gap = 44
    font = _font(94)
    text1, text2 = "Video", "Enhancer"
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    text_w = int(max(tmp.textlength(text1, font=font),
                     tmp.textlength(text2, font=font)))
    W = pad + b + gap + text_w + pad
    H = pad + b + pad

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.alpha_composite(badge(1024).resize((b, b), Image.LANCZOS), (pad, pad))

    d = ImageDraw.Draw(img)
    tx = pad + b + gap
    d.text((tx, pad + 22), text1, font=font, fill=ACCENT)
    d.text((tx, pad + 22 + 102), text2, font=font, fill=ACCENT_LT)
    return img


def main():
    ASSETS.mkdir(exist_ok=True)
    master = badge(1024)

    master.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon.png")
    master.resize((256, 256), Image.LANCZOS).save(
        ASSETS / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
               (128, 128), (256, 256)])
    lockup().save(ASSETS / "logo.png")
    print("wrote icon.ico, icon.png, logo.png to", ASSETS)


if __name__ == "__main__":
    main()
