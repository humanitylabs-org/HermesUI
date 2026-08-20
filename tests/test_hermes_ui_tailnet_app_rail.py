import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
JS = (ROOT / "static" / "tailnet-app-rail.js").read_text(encoding="utf-8")
BOOT = (ROOT / "static" / "boot.js").read_text(encoding="utf-8")
SWIPE = (ROOT / "static" / "session-swipe-navigation.js").read_text(encoding="utf-8")
GITIGNORE = (ROOT / ".gitignore").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
FRAME_BRIDGE = (ROOT / "hermesui" / "support" / "tailnet-frame" / "index.html").read_text(encoding="utf-8")


def _rail_markup() -> str:
    start = INDEX.index('<nav class="rail tailnet-app-rail"')
    end = INDEX.index("</nav>", start)
    return INDEX[start:end]


def _clean_app(raw):
    node = shutil.which("node")
    assert node, "Node.js is required for the Tailnet app parser contract test"
    start = JS.index("  function cleanApp(raw){")
    end = JS.index("\n  function closeSessionsOverlay", start)
    clean_app_source = JS[start:end]
    harness = f"""
const document={{baseURI:'https://host.example/hermesUI/'}};
const location=new URL('https://host.example/hermesUI/');
const ICONS={{apps:'icon',link:'icon'}};
{clean_app_source}
const result=cleanApp(JSON.parse(process.argv[1]));
process.stdout.write(JSON.stringify(result));
"""
    proc = subprocess.run(
        [node, "-e", harness, json.dumps(raw)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_old_webui_panel_tabs_are_not_in_the_desktop_rail():
    rail = _rail_markup()
    assert 'aria-label="Wizard OS apps"' in rail
    assert "data-panel=" not in rail
    assert "switchPanel(" not in rail


def test_hermes_ui_is_the_first_and_current_rail_item():
    rail = _rail_markup()
    assert rail.index('data-tooltip="Hermes UI"') < rail.index('id="tailnetAppLinks"')
    assert 'aria-current="page"' in rail
    assert 'href="./"' in rail
    assert 'class="tailnet-app-home-icon"' in rail
    assert 'width="34" height="34"' in rail
    assert ".tailnet-app-home-icon{display:block;width:34px;height:34px" in CSS
    assert ".tailnet-app-icon{width:20px;height:20px" in CSS


def test_app_selector_has_three_ordered_groups_and_add_controls():
    rail = _rail_markup()
    private = rail.index('id="tailnetPrivateAppsLabel"')
    company = rail.index('id="tailnetCompanyAppsLabel"')
    public = rail.index('id="tailnetPublicAppsLabel"')
    assert private < company < public
    assert '<span class="tailnet-app-group-badge" aria-hidden="true">PRIVATE</span>' in rail
    assert '<span class="tailnet-app-group-badge" aria-hidden="true">WORK</span>' in rail
    assert '<span class="tailnet-app-group-badge" aria-hidden="true">WEB</span>' in rail
    assert 'aria-label="Private Tailnet apps"' in rail
    assert 'aria-label="Work apps"' in rail
    assert 'aria-label="Web bookmarks"' in rail
    assert 'id="tailnetPrivateAdd"' in rail
    assert 'id="tailnetCompanyAdd"' in rail
    assert 'id="tailnetPublicAdd"' in rail
    assert 'id="tailnetCompanyAppLinks"' in rail
    assert 'id="tailnetPublicAppLinks"' in rail
    assert rail.index('id="tailnetAppLinks"') < rail.index('id="tailnetPrivateAdd"')
    assert rail.index('id="tailnetCompanyAppLinks"') < rail.index('id="tailnetCompanyAdd"')
    assert rail.index('id="tailnetPublicAppLinks"') < rail.index('id="tailnetPublicAdd"')


def test_work_and_web_entries_are_browser_local_panel_buttons():
    assert "const BOOKMARK_STORAGE_KEY='hermesui.app-selector.bookmarks.v1'" in JS
    assert "localStorage.getItem(BOOKMARK_STORAGE_KEY)" in JS
    assert "localStorage.setItem(BOOKMARK_STORAGE_KEY" in JS
    assert "showPromptDialog" in JS
    assert "addSavedApp('company')" in JS
    assert "addSavedApp('public')" in JS
    assert "link.dataset.bookmarkGroup=group" in JS
    bookmark_renderer = JS[JS.index("function renderBookmark"):JS.index("function containerForGroup")]
    assert "document.createElement('button')" in bookmark_renderer
    assert "activateApp(app)" in bookmark_renderer
    assert "bindBookmarkActions(link)" in bookmark_renderer
    assert "link.setAttribute('aria-haspopup','menu')" in bookmark_renderer
    assert "target='_blank'" not in JS
    assert "window.open(" not in JS
    assert "The selector does not create new tabs or windows." in README


def test_saved_bookmark_urls_are_https_only_and_credentials_are_rejected():
    assert "if(!URL_SCHEME_RE.test(value))value=`https://${value}`" in JS
    assert "url.protocol!=='https:'" in JS
    assert "url.username||url.password" in JS
    assert "That address must be a safe HTTPS URL." in JS


def test_group_list_scrolls_inside_the_fixed_rail():
    assert ".rail.tailnet-app-rail{display:flex!important;order:1;position:relative;z-index:240;overflow:hidden;}" in CSS
    assert ".tailnet-app-groups{width:100%;min-height:0;flex:1 1 auto;" in CSS
    assert "overflow-y:auto" in CSS[CSS.index(".tailnet-app-groups{"):CSS.index("}", CSS.index(".tailnet-app-groups{"))]
    assert ".tailnet-app-group{width:100%;display:flex;flex-direction:column" in CSS


def test_private_app_inventory_is_local_config_not_public_source():
    assert "tailnet-apps.json" in JS
    assert "static/tailnet-apps.json" in GITIGNORE.splitlines()
    assert ".ts.net" not in INDEX
    assert ".ts.net" not in JS


def test_every_selector_app_switches_inside_the_private_shell_without_direct_open_fallback():
    assert "target='_blank'" not in JS
    assert "noopener noreferrer" not in JS
    assert "link.addEventListener('click'" in JS
    assert "activateApp(app)" in JS
    assert "link.dataset.tailnetAppId=app.id" in JS
    assert "frameUrl.origin!==location.origin" in JS
    assert "url.protocol!=='https:'&&url.origin!==location.origin" in JS


def test_private_plus_is_the_humanity_labs_panel_marketplace_placeholder():
    assert "id:'private-marketplace'" in JS
    assert "href:'https://humanitylabs.org/'" in JS
    assert "frameHref:new URL('/tailnet-frame/?app=private-marketplace',location.origin).href" in JS
    assert "privateAdd.addEventListener('click',()=>activateApp(privateMarketplace))" in JS
    assert "if(id==='private-marketplace')return {label:'Private app library',href:'https://humanitylabs.org/'}" in FRAME_BRIDGE


def test_same_origin_frame_bridge_resolves_only_valid_saved_work_and_web_entries():
    assert "const GROUPS=new Set(['company','public'])" in FRAME_BRIDGE
    assert "localStorage.getItem(BOOKMARK_STORAGE_KEY)" in FRAME_BRIDGE
    assert "payload.version!==1" in FRAME_BRIDGE
    assert "url.protocol!=='https:'||url.username||url.password" in FRAME_BRIDGE
    assert "return cleanDestination(entries.find(item=>item&&item.id===id))" in FRAME_BRIDGE
    assert "frame.src=app.href" in FRAME_BRIDGE
    assert "target=\"_blank\"" not in FRAME_BRIDGE
    assert "window.open(" not in FRAME_BRIDGE
    assert "vnc_auto" not in FRAME_BRIDGE
    assert "websockify" not in FRAME_BRIDGE
    assert "openInTailnetBrowser" not in FRAME_BRIDGE
    assert "fetch('./navigate'" not in FRAME_BRIDGE
    assert "?bookmark=${encodeURIComponent(`${group}:${id}`)}" in JS


def test_app_tooltips_escape_the_clipped_rail_and_bookmarks_have_two_actions():
    assert "document.body.appendChild(tooltip)" in JS
    assert "tooltip.className='tailnet-rail-tooltip'" in JS
    assert ".tailnet-rail-tooltip{position:fixed;z-index:10000" in CSS
    assert ".tailnet-app-rail .has-tooltip::after{display:none!important;}" in CSS
    assert "button.addEventListener('contextmenu'" in JS
    context_source = JS[JS.index("button.addEventListener('contextmenu'"):JS.index("button.addEventListener('pointerdown'")]
    assert "suppressBookmarkActivation" not in context_source
    assert "setTimeout(()=>{" in JS and "},550)" in JS
    menu_source = JS[JS.index("function ensureBookmarkMenu"):JS.index("function openBookmarkMenu")]
    assert "rename.textContent='Rename'" in menu_source
    assert "remove.textContent='Delete'" in menu_source
    assert menu_source.count("setAttribute('role','menuitem')") == 2
    assert ".tailnet-bookmark-menu button{min-height:44px;}" in CSS


def test_documented_app_entry_normalizes_to_direct_and_embedded_destinations():
    assert '"frameHref": "/tailnet-frame/?app=private-app"' in README
    app = _clean_app(
        {
            "id": "private-app",
            "label": "Private App",
            "href": "https://device.example.ts.net/private-app/",
            "frameHref": "/tailnet-frame/?app=private-app",
            "icon": "apps",
        }
    )
    assert app == {
        "id": "private-app",
        "label": "Private App",
        "href": "https://device.example.ts.net/private-app/",
        "frameHref": "https://host.example/tailnet-frame/?app=private-app",
        "icon": "apps",
    }
    assert "frame.src=app.frameHref" in JS


def test_required_app_urls_are_rejected_before_url_coercion():
    valid = {
        "id": "private-app",
        "label": "Private App",
        "href": "https://device.example.ts.net/private-app/",
        "frameHref": "/tailnet-frame/?app=private-app",
        "icon": "apps",
    }
    for field in ("href", "frameHref"):
        missing = dict(valid)
        missing.pop(field)
        assert _clean_app(missing) is None
        for invalid in (None, "", "   ", 42):
            malformed = {**valid, field: invalid}
            assert _clean_app(malformed) is None
    assert _clean_app({**valid, "frameHref": "https://other.example/frame"}) is None


def test_workspace_and_hermes_selector_are_wired_into_the_layout():
    assert 'id="tailnetAppWorkspace"' in INDEX
    assert 'id="tailnetAppFrame"' in INDEX
    assert 'id="tailnetAppHome"' in INDEX
    assert "data-tailnet-view" in JS


def test_rail_is_persistent_and_the_external_workspace_is_responsive():
    assert ".rail.tailnet-app-rail{display:flex!important;" in CSS
    assert ".rail.tailnet-app-rail{display:none!important;}" not in CSS
    assert "@media(min-width:1296px)" in CSS
    assert "@media(max-width:1295px)" in CSS
    assert "@media(min-width:900px)" not in CSS
    assert "@media(min-width:1500px)" not in CSS
    assert "flex:0 0 50vw;width:50vw;max-width:50vw" in CSS
    assert "html[data-tailnet-view=\"external\"] .tailnet-app-workspace" in CSS
    assert "html[data-tailnet-view=\"external\"] .layout > .sidebar" in CSS
    assert ".sidebar-nav{display:none!important;}" in CSS


def test_external_app_is_the_only_mobile_content_beside_the_persistent_selector():
    assert '@media(max-width:640px),(pointer:coarse)' in CSS
    assert 'html[data-tailnet-view="external"] .app-titlebar{display:none!important;}' in CSS
    assert 'html[data-tailnet-view="external"] .tailnet-app-workspace{display:block;order:2;flex:1 1 auto;width:auto;max-width:none;}' in CSS
    assert 'html[data-tailnet-view="external"] .layout > .sidebar' in CSS
    assert 'html[data-tailnet-view="external"] .layout > .main' in CSS
    assert 'html[data-tailnet-view="external"] .layout > .rightpanel{display:none!important;}' in CSS
    assert 'html[data-tailnet-view="external"] .tailnet-app-rail' in CSS


def test_mobile_app_selector_is_fixed_and_sessions_are_a_real_page():
    assert (
        '.rail.tailnet-app-rail{position:fixed;left:0;top:0;bottom:0;width:48px;'
        'height:100%;height:100dvh;box-sizing:border-box;'
        in CSS
    )
    assert '.layout{margin-left:48px;width:calc(100% - 48px);}' in CSS
    assert (
        'html:not([data-tailnet-view="external"]) .app-titlebar{'
        'margin-left:48px;width:calc(100% - 48px);box-sizing:border-box;}'
        in CSS
    )
    assert (
        'html:not([data-tailnet-view="external"]) .sidebar{left:48px;'
        'width:calc(100vw - 48px);transform:translateX(calc(-100% - 48px));}'
        in CSS
    )
    assert (
        'html:not([data-tailnet-view="external"]) .sidebar.mobile-open{'
        'transform:translateX(0);}'
        in CSS
    )
    assert INDEX.index('id="btnHamburger"') < INDEX.index('id="mobileSessionTabs"')
    assert "function openMobileSessionPage()" in BOOT
    assert "openMobileSessionPage();" in BOOT
    assert "document.documentElement.dataset.mobileSessionView='sessions';" in BOOT
    assert "if(_mobileSessionSelectionRequired())return openMobileSessionPage();" in BOOT
    assert "if(typeof openMobileSessionPage==='function') openMobileSessionPage();" in BOOT
    assert "if(typeof syncMobileSessionNavigation==='function') syncMobileSessionNavigation();" in SWIPE
    assert 'html[data-mobile-session-view="sessions"] .app-titlebar{display:none!important;}' in CSS
    assert '.sidebar.mobile-session-page .mobile-sidebar-close{display:none!important;}' in CSS
    assert '.sidebar.mobile-session-page .panel-view{margin-left:0;}' in CSS


def test_tailnet_rail_script_is_loaded_from_the_mount_aware_base():
    assert 'src="static/tailnet-app-rail.js?v=__WEBUI_VERSION__"' in INDEX
    assert "new URL(CONFIG_PATH,document.baseURI||location.href)" in JS