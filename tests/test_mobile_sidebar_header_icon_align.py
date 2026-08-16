"""Mobile sidebar close control uses a mirrored hamburger/menu glyph."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STYLE = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


def test_mobile_close_uses_mirrored_menu_instead_of_x():
    start = HTML.index('class="panel-head-btn mobile-sidebar-close')
    end = HTML.index("</button>", start)
    close_button = HTML[start:end]
    assert 'class="mobile-sidebar-close-icon"' in close_button
    assert '<polyline points="7 9 4 12 7 15"/>' in close_button
    assert 'x1="18" y1="6" x2="6" y2="18"' not in close_button
    assert ".panel-head-btn.mobile-sidebar-close svg{width:24px;height:24px" in STYLE


def test_mobile_close_is_centered_and_keeps_tap_target():
    close_rule = STYLE[STYLE.index(".panel-head-btn.mobile-sidebar-close{"):]
    close_rule = close_rule[: close_rule.index("}") + 1]
    # Glyph centered in the button.
    assert "align-items:center" in close_rule and "justify-content:center" in close_rule
    # 44x44 tap target preserved for mobile touch.
    assert "width:44px!important;height:44px!important" in close_rule
    # Keeps the safe-area offset (so it still clears the notch) — no extra blank
    # drawer padding.
    assert "var(--app-titlebar-safe-top)" in close_rule


def test_mobile_close_hidden_on_desktop():
    # Base (non-media) rule hides the close control on desktop.
    assert ".mobile-sidebar-close{display:none;}" in STYLE
