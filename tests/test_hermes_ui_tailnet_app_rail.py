from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
JS = (ROOT / "static" / "tailnet-app-rail.js").read_text(encoding="utf-8")
GITIGNORE = (ROOT / ".gitignore").read_text(encoding="utf-8")


def _rail_markup() -> str:
    start = INDEX.index('<nav class="rail tailnet-app-rail"')
    end = INDEX.index("</nav>", start)
    return INDEX[start:end]


def test_old_webui_panel_tabs_are_not_in_the_desktop_rail():
    rail = _rail_markup()
    assert 'aria-label="Tailnet apps"' in rail
    assert "data-panel=" not in rail
    assert "switchPanel(" not in rail


def test_hermes_ui_is_the_first_and_current_rail_item():
    rail = _rail_markup()
    assert rail.index('data-tooltip="Hermes UI"') < rail.index('id="tailnetAppLinks"')
    assert 'aria-current="page"' in rail
    assert 'href="./"' in rail


def test_private_app_inventory_is_local_config_not_public_source():
    assert "tailnet-apps.json" in JS
    assert "static/tailnet-apps.json" in GITIGNORE.splitlines()
    assert ".ts.net" not in INDEX
    assert ".ts.net" not in JS


def test_external_apps_switch_inside_the_private_shell_with_direct_open_fallback():
    assert "link.target='_blank'" in JS
    assert "link.rel='noopener noreferrer'" in JS
    assert "link.addEventListener('click'" in JS
    assert "activateApp(app)" in JS
    assert "link.dataset.tailnetAppId=app.id" in JS
    assert "frameUrl.origin!==location.origin" in JS
    assert "url.protocol!=='https:'&&url.origin!==location.origin" in JS


def test_workspace_and_hermes_selector_are_wired_into_the_layout():
    assert 'id="tailnetAppWorkspace"' in INDEX
    assert 'id="tailnetAppFrame"' in INDEX
    assert 'id="tailnetAppHome"' in INDEX
    assert "data-tailnet-view" in JS


def test_rail_is_persistent_and_the_external_workspace_is_responsive():
    assert ".rail.tailnet-app-rail{display:flex!important;" in CSS
    assert ".rail.tailnet-app-rail{display:none!important;}" not in CSS
    assert "@media(min-width:900px)" in CSS
    assert "@media(max-width:899px)" in CSS
    assert "@media(min-width:1500px)" not in CSS
    assert "html[data-tailnet-view=\"external\"] .tailnet-app-workspace" in CSS
    assert "html[data-tailnet-view=\"external\"] .layout > .sidebar" in CSS
    assert ".sidebar-nav{display:none!important;}" in CSS


def test_tailnet_rail_script_is_loaded_from_the_mount_aware_base():
    assert 'src="static/tailnet-app-rail.js?v=__WEBUI_VERSION__"' in INDEX
    assert "new URL(CONFIG_PATH,document.baseURI||location.href)" in JS