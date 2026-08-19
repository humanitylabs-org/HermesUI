from pathlib import Path
import json
import struct


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
SHARE = (STATIC / "share.html").read_text(encoding="utf-8")
MESSAGES = (STATIC / "messages.js").read_text(encoding="utf-8")
SW = (STATIC / "sw.js").read_text(encoding="utf-8")
MANIFEST = json.loads((STATIC / "manifest.json").read_text(encoding="utf-8"))


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_wizard_hat_vector_family_is_present_and_identifiable():
    tile = (STATIC / "wizard-hat.svg").read_text(encoding="utf-8")
    mark = (STATIC / "wizard-hat-mark.svg").read_text(encoding="utf-8")
    for source in (tile, mark):
        assert 'data-brand="wizard-hat"' in source
        assert "wizard-mark" in source
        assert "wizard-star" in source
    assert "wizard-tile" in tile
    assert "wizard-tile" not in mark


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
    assert 'rel="icon" type="image/svg+xml" href="static/wizard-hat.svg"' in INDEX
    assert 'rel="shortcut icon" href="static/wizard-hat.ico"' in INDEX
    assert 'rel="apple-touch-icon" sizes="512x512" href="static/wizard-hat-apple-touch.png"' in INDEX
    assert 'id="tailnetAppHome"' in INDEX
    assert 'class="tailnet-app-home-icon" src="static/wizard-hat.svg"' in INDEX
    assert 'class="wizard-brand-icon" src="static/wizard-hat.svg"' in INDEX
    assert 'class="wizard-brand-mark" src="static/wizard-hat-mark.svg"' in INDEX
    assert 'aria-label="Wizard hat"' in INDEX
    assert "Hermes caduceus" not in INDEX
    assert "app-titlebar-mark" not in INDEX
    assert "hermes-mark" not in INDEX


def test_share_header_notifications_and_worker_use_the_wizard_hat():
    assert "'+root+'static/wizard-hat.svg" in SHARE
    assert 'class="wizard-brand-icon" id="shareBrandIcon"' in SHARE
    assert "document.getElementById('shareBrandIcon').src=root+'static/wizard-hat.svg'" in SHARE
    assert "share-mark" not in SHARE
    assert "icon:'static/wizard-hat-192.png'" in MESSAGES
    assert "badge:'static/wizard-hat-32.png'" in MESSAGES
    assert "./static/wizard-hat.svg" in SW
    assert "./static/wizard-hat-32.png" in SW


def test_manifest_and_raster_assets_are_a_coherent_wizard_hat_family():
    manifest_icons = {icon["src"] for icon in MANIFEST["icons"]}
    assert manifest_icons == {
        "static/wizard-hat.svg",
        "static/wizard-hat-32.png",
        "static/wizard-hat-192.png",
        "static/wizard-hat-512.png",
    }
    assert MANIFEST["shortcuts"][0]["icons"][0]["src"] == "static/wizard-hat-192.png"
    assert _png_size(STATIC / "wizard-hat-32.png") == (32, 32)
    assert _png_size(STATIC / "wizard-hat-192.png") == (192, 192)
    assert _png_size(STATIC / "wizard-hat-512.png") == (512, 512)
    assert _png_size(STATIC / "wizard-hat-apple-touch.png") == (512, 512)
    ico = (STATIC / "wizard-hat.ico").read_bytes()
    assert ico[:4] == b"\x00\x00\x01\x00"
    assert struct.unpack("<H", ico[4:6])[0] >= 4
