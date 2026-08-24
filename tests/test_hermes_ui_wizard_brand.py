from pathlib import Path
import base64
import hashlib
import json
import re
import struct


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
SHARE = (STATIC / "share.html").read_text(encoding="utf-8")
MESSAGES = (STATIC / "messages.js").read_text(encoding="utf-8")
SW = (STATIC / "sw.js").read_text(encoding="utf-8")
MANIFEST = json.loads((STATIC / "manifest.json").read_text(encoding="utf-8"))
SOURCE_SHA256 = "fbde3ed59d1a4f03c0bc602770501ed6eb88dc4a437e3a5d2081dee9f6ffc5e5"


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


def _embedded_png(source: str) -> bytes:
    match = re.search(r'href="data:image/png;base64,([A-Za-z0-9+/=]+)"', source)
    assert match is not None
    return base64.b64decode(match.group(1))


def test_exact_user_supplied_artwork_is_the_canonical_source():
    source = STATIC / "wizard-hat-source.png"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == SOURCE_SHA256
    assert _png_size(source) == (1182, 1331)


def test_svg_compatibility_wrappers_embed_the_supplied_artwork_family():
    png_512 = (STATIC / "wizard-hat-512.png").read_bytes()
    for name in ("wizard-hat.svg", "wizard-hat-mark.svg"):
        source = (STATIC / name).read_text(encoding="utf-8")
        assert 'data-brand="wizard-hat"' in source
        assert 'data-artwork="user-supplied-wizard-v1"' in source
        assert f'data-raster-sha256="{hashlib.sha256(png_512).hexdigest()}"' in source
        assert _embedded_png(source) == png_512
        assert "crooked-crown" not in source


def test_legacy_icon_routes_are_exact_wizard_hat_aliases():
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
        assert (STATIC / alias).read_bytes() == (STATIC / canonical).read_bytes()


def test_all_visible_shell_brand_surfaces_use_the_wizard_hat():
    assert 'rel="icon" type="image/png" sizes="32x32" href="static/wizard-hat-32.png"' in INDEX
    assert 'rel="shortcut icon"' not in INDEX
    assert 'rel="apple-touch-icon" sizes="512x512" href="static/wizard-hat-apple-touch.png"' in INDEX
    assert 'id="tailnetAppHome"' in INDEX
    assert 'class="tailnet-app-home-icon" src="static/wizard-hat-32.png"' in INDEX
    assert 'class="wizard-brand-icon" src="static/wizard-hat-32.png"' in INDEX
    assert 'class="wizard-brand-mark" src="static/wizard-hat-192.png"' in INDEX
    assert 'aria-label="Wizard hat"' in INDEX
    assert "Hermes caduceus" not in INDEX
    assert "hm-g0" not in INDEX


def test_share_header_notifications_and_worker_use_the_wizard_hat():
    assert "'+root+'static/wizard-hat-32.png" in SHARE
    assert 'class="wizard-brand-icon" id="shareBrandIcon"' in SHARE
    assert "document.getElementById('shareBrandIcon').src=root+'static/wizard-hat-192.png'" in SHARE
    assert "share-mark" not in SHARE
    assert "icon:'static/wizard-hat-192.png'" in MESSAGES
    assert "badge:'static/wizard-hat-32.png'" in MESSAGES
    for asset in (
        "wizard-hat-32.png",
        "wizard-hat-192.png",
    ):
        assert f"./static/{asset}" in SW
    for deferred_asset in (
        "wizard-hat.svg",
        "wizard-hat-mark.svg",
        "wizard-hat-512.png",
        "wizard-hat-maskable-192.png",
        "wizard-hat-maskable-512.png",
        "wizard-hat-apple-touch.png",
        "wizard-hat.ico",
    ):
        assert f"./static/{deferred_asset}" not in SW
    assert "wizard-hat-source.png" not in SW


def test_manifest_and_raster_assets_use_complete_any_and_maskable_families():
    manifest_icons = {icon["src"]: icon.get("purpose") for icon in MANIFEST["icons"]}
    assert manifest_icons == {
        "static/wizard-hat-32.png": "any",
        "static/wizard-hat-192.png": "any",
        "static/wizard-hat-512.png": "any",
        "static/wizard-hat-maskable-192.png": "maskable",
        "static/wizard-hat-maskable-512.png": "maskable",
    }
    assert MANIFEST["shortcuts"][0]["icons"][0]["src"] == "static/wizard-hat-192.png"
    expected_sizes = {
        "wizard-hat-32.png": (32, 32),
        "wizard-hat-192.png": (192, 192),
        "wizard-hat-512.png": (512, 512),
        "wizard-hat-maskable-192.png": (192, 192),
        "wizard-hat-maskable-512.png": (512, 512),
        "wizard-hat-apple-touch.png": (512, 512),
    }
    for name, size in expected_sizes.items():
        assert _png_size(STATIC / name) == size
    assert (STATIC / "wizard-hat-apple-touch.png").read_bytes() == (
        STATIC / "wizard-hat-maskable-512.png"
    ).read_bytes()
    ico = (STATIC / "wizard-hat.ico").read_bytes()
    assert ico[:4] == b"\x00\x00\x01\x00"
    assert struct.unpack("<H", ico[4:6])[0] >= 7
