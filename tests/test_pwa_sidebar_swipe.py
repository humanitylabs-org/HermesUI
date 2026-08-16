from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOT_JS = (ROOT / "static" / "boot.js").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
STYLE_CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
SWIPE_JS = (ROOT / "static" / "session-swipe-navigation.js").read_text(encoding="utf-8")


def test_mobile_sidebar_is_hamburger_only():
    assert 'id="btnHamburger"' in INDEX_HTML
    assert 'onclick="toggleMobileSidebar()"' in INDEX_HTML
    assert "function toggleMobileSidebar()" in BOOT_JS
    assert "function closeMobileSidebar()" in BOOT_JS

    assert 'id="pwaSidebarEdgeGuard"' not in INDEX_HTML
    assert "pwa-sidebar-edge-guard" not in STYLE_CSS
    assert "_installPwaSidebarSwipeGesture" not in BOOT_JS
    assert "_openMobileSidebarFromGesture" not in BOOT_JS
    assert "_onPwaSidebarSwipe" not in BOOT_JS
    assert "_PWA_SIDEBAR_SWIPE" not in BOOT_JS


def test_horizontal_mobile_gestures_are_reserved_for_session_navigation():
    assert 'static/session-swipe-navigation.js?v=__WEBUI_VERSION__' in INDEX_HTML
    assert "surface.addEventListener('pointerdown',start,{passive:true})" in SWIPE_JS
    assert "window.addEventListener('pointermove',move,{passive:false})" in SWIPE_JS
    assert "_openSidebarSession(target,{source})" in SWIPE_JS
    assert "mobile-session-swipe" in SWIPE_JS
    assert "mobile-session-tab" in SWIPE_JS


def test_session_swipe_does_not_disable_horizontal_scrollers_globally():
    compact = STYLE_CSS.replace(" ", "")
    assert "html{touch-action" not in compact
    assert "body{touch-action" not in compact
    assert ".layout{touch-action" not in compact
