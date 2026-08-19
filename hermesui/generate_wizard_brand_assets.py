#!/usr/bin/env python3
"""Generate the HermesUI wizard brand family from its approved PNG source."""

from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path

from PIL import Image

SOURCE_SHA256 = "fbde3ed59d1a4f03c0bc602770501ed6eb88dc4a437e3a5d2081dee9f6ffc5e5"
TRANSPARENT_FILL = 0.94
MASKABLE_FILL = 0.74


def _resample():
    return Image.Resampling.LANCZOS


def _load_source(path: Path) -> Image.Image:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SOURCE_SHA256:
        raise SystemExit(
            f"source SHA-256 mismatch: expected {SOURCE_SHA256}, got {digest}"
        )
    image = Image.open(path).convert("RGBA")
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise SystemExit("source image is fully transparent")
    return image.crop(bbox)


def _fit(image: Image.Image, size: int, fill: float) -> Image.Image:
    max_side = max(image.size)
    scale = (size * fill) / max_side
    target = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    resized = image.resize(target, _resample())
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset = ((size - target[0]) // 2, (size - target[1]) // 2)
    canvas.alpha_composite(resized, offset)
    return canvas


def _maskable_background(size: int) -> Image.Image:
    # Full-bleed background for Android maskable and Apple touch icons.
    image = Image.new("RGBA", (size, size))
    px = image.load()
    if px is None:
        raise RuntimeError("could not allocate maskable icon pixels")
    inner = (27, 20, 78)
    outer = (7, 6, 27)
    center_x = size * 0.48
    center_y = size * 0.40
    max_distance = (center_x**2 + center_y**2) ** 0.5
    for y in range(size):
        for x in range(size):
            distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
            t = min(1.0, distance / max_distance)
            # Ease the vignette so the center remains rich rather than flat.
            t = t * t * (3.0 - 2.0 * t)
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(inner, outer)) + (255,)
    return image


def _maskable(image: Image.Image, size: int) -> Image.Image:
    canvas = _maskable_background(size)
    fitted = _fit(image, size, MASKABLE_FILL)
    canvas.alpha_composite(fitted)
    return canvas


def _save_png(image: Image.Image, path: Path) -> None:
    image.save(path, format="PNG", optimize=True, compress_level=9)


def _svg_wrapper(png_bytes: bytes, label: str) -> str:
    encoded = base64.b64encode(png_bytes).decode("ascii")
    source_hash = hashlib.sha256(png_bytes).hexdigest()
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" '
        f'role="img" aria-label="{label}" data-brand="wizard-hat" '
        'data-artwork="user-supplied-wizard-v1" '
        f'data-raster-sha256="{source_hash}">\n'
        f'  <image width="512" height="512" preserveAspectRatio="xMidYMid meet" '
        f'href="data:image/png;base64,{encoded}"/>\n'
        '</svg>\n'
    )


def generate(static_dir: Path) -> None:
    source_path = static_dir / "wizard-hat-source.png"
    source = _load_source(source_path)

    transparent = {}
    for size in (32, 192, 512):
        rendered = _fit(source, size, TRANSPARENT_FILL)
        transparent[size] = rendered
        _save_png(rendered, static_dir / f"wizard-hat-{size}.png")

    for size in (192, 512):
        _save_png(_maskable(source, size), static_dir / f"wizard-hat-maskable-{size}.png")

    apple = _maskable(source, 512)
    _save_png(apple, static_dir / "wizard-hat-apple-touch.png")

    ico_sizes = (16, 24, 32, 48, 64, 128, 256)
    ico_frames = [_fit(source, size, TRANSPARENT_FILL) for size in ico_sizes]
    ico_frames[-1].save(
        static_dir / "wizard-hat.ico",
        format="ICO",
        sizes=[(size, size) for size in ico_sizes],
        append_images=ico_frames[:-1],
    )

    png_512 = (static_dir / "wizard-hat-512.png").read_bytes()
    (static_dir / "wizard-hat.svg").write_text(
        _svg_wrapper(png_512, "Wizard"), encoding="utf-8"
    )
    (static_dir / "wizard-hat-mark.svg").write_text(
        _svg_wrapper(png_512, "Wizard"), encoding="utf-8"
    )

    aliases = {
        "favicon.svg": "wizard-hat.svg",
        "favicon-512.svg": "wizard-hat.svg",
        "favicon-32.png": "wizard-hat-32.png",
        "favicon-192.png": "wizard-hat-192.png",
        "favicon-512.png": "wizard-hat-512.png",
        "apple-touch-icon.png": "wizard-hat-apple-touch.png",
        "favicon.ico": "wizard-hat.ico",
    }
    for alias, canonical in aliases.items():
        (static_dir / alias).write_bytes((static_dir / canonical).read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "static_dir",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "static",
    )
    args = parser.parse_args()
    generate(args.static_dir.resolve())
