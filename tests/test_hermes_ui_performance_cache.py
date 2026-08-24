"""HermesUI repeat-load performance cache contracts."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SW = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
RAIL = (ROOT / "static" / "tailnet-app-rail.js").read_text(encoding="utf-8")
SESSIONS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")


def test_versioned_shell_cache_is_served_before_background_revalidation():
    marker = "// stale-while-revalidate is safe here"
    start = SW.index(marker)
    block = SW[start : start + 1600]
    assert "const refresh = fetch(new Request(event.request, { cache: 'no-store' })).then" in block
    assert "event.waitUntil(refresh.then(() => undefined, () => undefined))" in block
    assert "caches.match(event.request).then((cached) => cached || refresh)" in block
    assert "performance-cache-v1" in SW


def test_api_navigation_and_auth_paths_remain_network_authoritative():
    api = SW.index("// API and streaming endpoints")
    navigation = SW.index("event.request.mode === 'navigate'")
    shell = SW.index("const shellPath")
    assert api < navigation < shell
    assert "url.pathname.includes('/api/')" in SW[api:navigation]
    assert "fetch(new Request(event.request, { cache: 'no-store' }))" in SW[navigation:shell]
    assert "SHELL_ASSETS.includes(shellPath)" in SW[shell:]


def test_shell_avoids_large_embedded_brand_wrappers_on_first_load():
    for unused in ("wizard-hat.svg", "wizard-hat-mark.svg", "wizard-hat.ico"):
        assert f'"static/{unused}"' not in INDEX
        assert f"'./static/{unused}'" not in SW
    assert 'src="static/wizard-hat-32.png"' in INDEX
    assert 'src="static/wizard-hat-192.png"' in INDEX


def test_startup_notifications_use_tab_cache_without_historical_output_sweep():
    assert "sessionStorage.getItem(NOTIFICATION_ITEMS_CACHE_KEY)" in RAIL
    assert "renderCronNotifications();\n    scheduleNotificationRefresh();" in RAIL
    assert "setNotificationsBadge(0);\n    void loadCronNotifications();" not in RAIL
    assert "fullRefresh:!notificationItems.size" in RAIL
    assert "cronNotificationWatermark(job,latestSessions)>Number(notificationWatermarks" in RAIL


def test_transcript_cache_and_deferred_model_refresh_protect_first_paint():
    assert "sessionStorage.setItem(_SESSION_MESSAGE_CACHE_STORAGE_KEY" in SESSIONS
    assert "localStorage.setItem(_SESSION_MESSAGE_CACHE_STORAGE_KEY" not in SESSIONS
    assert "_SESSION_MESSAGE_CACHE_STORAGE_MAX_CHARS = 1500000" in SESSIONS
    assert "_SESSION_MESSAGE_CACHE_ENTRY_MAX_CHARS = 350000" in SESSIONS
    assert "populateModelDropdown({freshness:'session_visit'});\n      },1200)" in SESSIONS
    assert "if(delayMs>0)setTimeout(queueIdle,delayMs)" in SESSIONS
