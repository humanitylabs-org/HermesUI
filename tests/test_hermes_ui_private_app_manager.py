from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
JS = (ROOT / "static" / "tailnet-app-manager.js").read_text(encoding="utf-8")
RAIL = (ROOT / "static" / "tailnet-app-rail.js").read_text(encoding="utf-8")
SW = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")


def test_app_manager_is_the_last_app_tile_before_marketplace():
    links = INDEX.index('id="tailnetAppLinks"')
    manager = INDEX.index('id="tailnetPrivateManager"')
    add = INDEX.index('id="tailnetPrivateAdd"')
    assert links < manager < add
    assert 'data-tailnet-app-id="private-app-manager"' in INDEX
    assert 'aria-label="App Manager"' in INDEX
    assert 'data-tooltip="App Manager"' in INDEX
    assert '<rect x="3" y="3" width="7" height="7" rx="1.5"/>' in INDEX
    assert 'tailnetAppManagerBadge' not in INDEX


def test_native_manager_panel_is_part_of_the_tailnet_workspace():
    workspace = INDEX.index('id="tailnetAppWorkspace"')
    frame = INDEX.index('id="tailnetAppFrame"')
    manager = INDEX.index('id="tailnetAppManager"')
    rail = INDEX.index('<nav class="rail tailnet-app-rail"')
    assert workspace < frame < manager < rail
    assert 'id="tailnetAppManagerList"' in INDEX
    assert 'id="tailnetAppManagerHidden"' in INDEX
    assert 'id="tailnetAppManagerHiddenCount"' in INDEX
    assert 'id="tailnetAppManagerHiddenList"' in INDEX
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
    assert "url.origin===location.origin" in JS
    assert "return !BLOCKED_PATHS.has(path);" in JS


def test_private_rail_has_no_preseeded_app_inventory():
    assert "static/tailnet-apps.json" not in RAIL
    assert "fetch(new URL(CONFIG_PATH" not in RAIL
    assert "privateCount:0" in RAIL
    assert 'src="static/tailnet-app-manager.js?v=__WEBUI_VERSION__&cron-notifications=v3&semantic-icons=v1&mobile-layer-nav=v1"' in INDEX


def test_approved_routes_keep_stable_detector_identity():
    assert "sourceKey.length>500" in JS
    assert "button.dataset.tailnetAppSourceKey=app.sourceKey" in JS
    assert "occupiedSourceKeys.has(app.sourceKey)" in JS
    assert "pinned.sourceKeys.has(app.actionKey)" in JS
    assert JS.count("if(statusPayload)renderStatus();") == 2
    assert "if(root.dataset.tailnetAppsReady==='true')syncInitialPrivateApps();" in JS


def test_service_worker_delivers_both_private_app_scripts_without_caching_apis():
    assert "'./static/tailnet-app-rail.js' + VQ + '&overlay=wizard-canvas-v8&bookmark-fallback=v5&bookmark-sync=v1&cron-notifications=v8&shell-theme=v1&private-only=v1&mobile-session-home=v1&cron-operations=v3&mobile-rail-right=v1&human-cron=v1&active-frequency=v1&scheduled-dashboard=v1&silent-notifications=v1&mobile-utility-menu=v1&mobile-bottom-menu=v1&mobile-collapsible-rail=v1&performance-cache=v1&notification-stream=v1&notification-hierarchy=v1&mobile-toggle-switches=v1&mobile-layer-nav=v1'" in SW
    assert "'./static/tailnet-app-manager.js' + VQ + '&cron-notifications=v3&semantic-icons=v1&mobile-layer-nav=v1'" in SW
    assert "url.pathname.includes('/api/')" in SW
    assert "return; // let browser handle normally" in SW


def test_manager_copy_is_concise_and_cards_expand_to_four_columns():
    assert '<h1 id="tailnetAppManagerTitle">App Manager</h1>' in INDEX
    assert INDEX.index('id="tailnetAppManagerOrigin"') < INDEX.index('id="tailnetAppManagerTitle"')
    assert 'Apps detected on this Tailnet node' not in INDEX
    assert 'Choose which ones appear' not in INDEX
    assert "setNotice(`${apps.length} app${apps.length===1?'':'s'}`);" in JS
    assert "state.textContent" not in JS
    assert "button('Add'" in JS
    assert "button('Remove'" in JS
    assert "Disable startup" not in JS
    assert "Start at boot" not in JS
    assert "setAutostart" not in JS
    assert '@container(min-width:680px){.tailnet-app-manager-list{grid-template-columns:repeat(4,minmax(0,1fr));}}' in CSS


def test_installed_apps_receive_opinionated_semantic_icons():
    assert "function semanticIconName(app)" in JS
    assert "if(/book|reader|document|compressor/.test(identity))return 'book'" in JS
    assert "if(/terminal|console|shell/.test(identity))return 'terminal'" in JS
    assert "if(/browser|web/.test(identity))return 'browser'" in JS
    assert JS.count("icon.innerHTML=semanticIcon(app);") == 2


def test_hidden_routes_are_transparent_but_read_only_and_collapsed():
    assert '<details class="tailnet-app-manager-hidden" id="tailnetAppManagerHidden" hidden>' in INDEX
    assert 'function managedHiddenRoutes()' in JS
    assert 'function renderHiddenRoutes()' in JS
    assert "statusPayload.serve.hiddenRoutes" in JS
    assert "hiddenPanel.hidden=!routes.length" in JS
    hidden_render = JS[JS.index('function renderHiddenRoutes()'):JS.index('function managedApps()')]
    assert "document.createElement('button')" not in hidden_render
    assert "runAction(" not in hidden_render
    assert "changePrivateApp(" not in hidden_render
