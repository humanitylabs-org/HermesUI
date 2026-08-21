from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
JS = (ROOT / "static" / "tailnet-app-manager.js").read_text(encoding="utf-8")
RAIL = (ROOT / "static" / "tailnet-app-rail.js").read_text(encoding="utf-8")
SW = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")


def test_manager_is_the_last_private_tile_before_plus():
    links = INDEX.index('id="tailnetAppLinks"')
    manager = INDEX.index('id="tailnetPrivateManager"')
    add = INDEX.index('id="tailnetPrivateAdd"')
    assert links < manager < add
    assert 'data-tailnet-app-id="private-app-manager"' in INDEX
    assert 'aria-label="Manage private apps"' in INDEX
    assert '<circle cx="12" cy="12" r="3"/>' in INDEX


def test_native_manager_panel_is_part_of_the_tailnet_workspace():
    workspace = INDEX.index('id="tailnetAppWorkspace"')
    frame = INDEX.index('id="tailnetAppFrame"')
    manager = INDEX.index('id="tailnetAppManager"')
    rail = INDEX.index('<nav class="rail tailnet-app-rail"')
    assert workspace < frame < manager < rail
    assert 'id="tailnetAppManagerList"' in INDEX
    assert '.tailnet-app-workspace iframe[hidden]{display:none!important;}' in CSS
    assert '.tailnet-app-manager[hidden]{display:none!important;}' in CSS


def test_manager_uses_only_adjacent_controller_endpoints():
    assert "const STATUS_PATH='/apps/api/status';" in JS
    assert "const PRIVATE_APPS_PATH='/apps/api/private-apps';" in JS
    assert "postJson('/apps/api/action'" in JS
    assert "credentials:'same-origin'" in JS
    assert "cache:'no-store'" in JS
    assert "localStorage" not in JS
    assert "CacheStorage" not in JS


def test_detected_apps_require_explicit_private_approval():
    assert "changePrivateApp(app,'remove')" in JS
    assert "changePrivateApp(app,'approve')" in JS
    assert "function appIsEligible(app)" in JS
    assert "if(!url||url.origin!==location.origin)return false;" in JS
    assert "return !BLOCKED_PATHS.has(path);" in JS


def test_manager_replaces_legacy_apps_manager_card_without_removing_fallback_config():
    assert "app.id==='apps-manager'" in RAIL
    assert "static/tailnet-apps.json" in RAIL
    assert 'src="static/tailnet-app-manager.js?v=__WEBUI_VERSION__"' in INDEX


def test_service_worker_delivers_both_private_app_scripts_without_caching_apis():
    assert "'./static/tailnet-app-rail.js' + VQ" in SW
    assert "'./static/tailnet-app-manager.js' + VQ" in SW
    assert "wizard-os-private-app-manager-v1" in SW
    assert "url.pathname.includes('/api/')" in SW
    assert "return; // let browser handle normally" in SW
