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
    assert 'aria-label="Detected"' in INDEX
    assert '<circle cx="12" cy="12" r="3"/>' in INDEX
    assert 'tailnetAppManagerBadge' not in INDEX


def test_native_manager_panel_is_part_of_the_tailnet_workspace():
    workspace = INDEX.index('id="tailnetAppWorkspace"')
    frame = INDEX.index('id="tailnetAppFrame"')
    manager = INDEX.index('id="tailnetAppManager"')
    rail = INDEX.index('<nav class="rail tailnet-app-rail"')
    assert workspace < frame < manager < rail
    assert 'id="tailnetAppManagerList"' in INDEX
    assert '.tailnet-app-workspace iframe[hidden]{display:none!important;}' in CSS
    assert '.tailnet-app-manager[hidden]{display:none!important;}' in CSS
    assert 'id="tailnetAppManagerOrigin"' in INDEX
    assert "const nodeUrl=new URL('/',location.origin);" in JS
    origin_css = CSS[CSS.index('.tailnet-app-manager-origin'):CSS.index('.tailnet-app-manager-origin:hover')]
    assert "overflow-wrap:anywhere" in origin_css
    assert "text-overflow:ellipsis" not in origin_css


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
    assert "url.hostname===location.hostname" in JS
    assert "return !BLOCKED_PATHS.has(path);" in JS


def test_private_rail_has_no_preseeded_app_inventory():
    assert "static/tailnet-apps.json" not in RAIL
    assert "fetch(new URL(CONFIG_PATH" not in RAIL
    assert "privateCount:0" in RAIL
    assert 'src="static/tailnet-app-manager.js?v=__WEBUI_VERSION__"' in INDEX


def test_approved_routes_keep_stable_detector_identity():
    assert "sourceKey.length>500" in JS
    assert "button.dataset.tailnetAppSourceKey=app.sourceKey" in JS
    assert "occupiedSourceKeys.has(app.sourceKey)" in JS
    assert "pinned.sourceKeys.has(app.actionKey)" in JS
    assert JS.count("if(statusPayload)renderStatus();") == 2
    assert "if(root.dataset.tailnetAppsReady==='true')syncInitialPrivateApps();" in JS


def test_service_worker_delivers_both_private_app_scripts_without_caching_apis():
    assert "'./static/tailnet-app-rail.js' + VQ" in SW
    assert "'./static/tailnet-app-manager.js' + VQ" in SW
    assert "wizard-os-private-app-manager-v3" in SW
    assert "url.pathname.includes('/api/')" in SW
    assert "return; // let browser handle normally" in SW


def test_manager_copy_is_concise_and_cards_expand_to_four_columns():
    assert '<h1 id="tailnetAppManagerTitle">Private apps</h1>' in INDEX
    assert INDEX.index('id="tailnetAppManagerOrigin"') < INDEX.index('id="tailnetAppManagerTitle"')
    assert 'Apps detected on this Tailnet node' not in INDEX
    assert 'Choose which ones appear' not in INDEX
    assert "setNotice(`${apps.length} app${apps.length===1?'':'s'}`);" in JS
    assert "state.textContent" not in JS
    assert "button('Add'" in JS
    assert "button('Remove'" in JS
    assert '@container(min-width:680px){.tailnet-app-manager-list{grid-template-columns:repeat(4,minmax(0,1fr));}}' in CSS
