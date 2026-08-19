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


def test_external_apps_open_safely_without_replacing_hermes_ui():
    assert "link.target='_blank'" in JS
    assert "link.rel='noopener noreferrer'" in JS
    assert "link.dataset.tailnetAppId=app.id" in JS
    assert "url.protocol!=='https:'&&url.origin!==location.origin" in JS


def test_rail_is_desktop_only_and_mobile_session_shell_stays_unchanged():
    assert ".rail.tailnet-app-rail{display:none!important;}" in CSS
    assert "@media(min-width:641px){.rail.tailnet-app-rail{display:flex!important;}}" in CSS
    assert ".sidebar-nav{display:none!important;}" in CSS


def test_tailnet_rail_script_is_loaded_from_the_mount_aware_base():
    assert 'src="static/tailnet-app-rail.js?v=__WEBUI_VERSION__"' in INDEX
    assert "new URL(CONFIG_PATH,document.baseURI||location.href)" in JS