import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
JS = (ROOT / "static" / "tailnet-app-rail.js").read_text(encoding="utf-8")
MANAGER = (ROOT / "static" / "tailnet-app-manager.js").read_text(encoding="utf-8")
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
    start = MANAGER.index("  function cleanApprovedApp(raw){")
    end = MANAGER.index("\n  function openPrivateApp", start)
    clean_app_source = MANAGER[start:end]
    harness = f"""
const location=new URL('https://host.example/hermesUI/');
{clean_app_source}
const result=cleanApprovedApp(JSON.parse(process.argv[1]));
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


def test_minimal_cron_notifications_live_below_wizard_before_private_apps():
    rail = _rail_markup()
    home = rail.index('id="tailnetAppHome"')
    bell = rail.index('id="tailnetNotificationsButton"')
    apps = rail.index('id="tailnetAppLinks"')
    assert home < bell < apps
    assert 'data-tailnet-app-id="cron-notifications"' in rail
    assert 'id="tailnetNotificationsBadge" hidden' in rail
    assert 'id="tailnetNotifications" aria-labelledby="tailnetNotificationsTitle" hidden' in INDEX
    assert 'id="tailnetNotificationsReadAll"' in INDEX
    assert INDEX.count('data-notification-filter=') == 2
    assert 'data-notification-filter="unread"' in INDEX
    assert 'data-notification-filter="all"' in INDEX
    assert "const NOTIFICATION_STATE_KEY='hermesui.cron-notifications.v1'" in JS
    assert "api('/api/crons')" in JS
    assert "/api/crons/output?job_id=" in JS
    assert "NOTIFICATION_LIST_LIMIT=40" in JS
    assert "notificationItems.values()).sort" not in JS  # sorting stays explicit and readable
    assert ".sort((left,right)=>right.modified-left.modified)" in JS
    assert "markNotificationRead(item)" in JS
    assert "markAllNotificationsRead" in JS
    assert "notificationFilter==='unread'?items.filter(notificationIsUnread):items" in JS
    assert "setNotificationFilter('unread')" in JS
    assert "hermesui:cron-completions" in JS
    assert "Status:\\*\\*\\s*silent" in JS
    assert "dividerIndex" in JS
    assert ".tailnet-notifications-badge" in CSS
    assert ".tailnet-notification-response" in CSS
    assert "notificationPreviewText" not in JS
    assert "response.textContent=notificationPreview(item.response)" in JS
    assert "Open to read" not in JS
    assert "if(open&&notificationIsUnread(item))" in JS
    assert "notificationState.readItems[item.key]" in JS
    assert "return (Number(notificationState.readItems[item.key])||0)<item.modified" in JS
    assert "notificationState.readJobs[item.jobId]=" not in JS
    assert "raw.version===1||raw.version===2" in JS
    assert "hydrateNotificationRich" in JS
    assert "renderMd(item.response)" in JS
    assert "postProcessRenderedMessages(body)" in JS
    assert "loadPdfInline(body)" in JS
    assert "rich.className='tailnet-notification-rich'" in JS
    assert "richBody.className='tailnet-notification-rich-body msg-body'" in JS
    assert "refreshCronNotificationBadge" not in JS
    assert "setNotificationsBadge(0);\n    void loadCronNotifications();" in JS
    assert "if(jobIds.length)void loadCronNotifications({jobIds});" in JS


def test_mode_theme_and_settings_controls_are_fixed_at_the_bottom_of_the_app_rail():
    rail = _rail_markup()
    groups = rail.index('id="tailnetAppGroups"')
    mode = rail.index('id="sessionViewToggle"')
    theme = rail.index('id="tailnetThemeToggle"')
    settings = rail.index('id="chatSettingsToggle"')
    assert groups < mode < theme < settings
    assert INDEX.count('id="sessionViewToggle"') == 1
    assert INDEX.count('id="chatSettingsToggle"') == 1
    assert 'aria-label="Turn High Signal mode on"' in rail
    assert 'tailnet-session-view-icon--signal' in rail
    assert 'tailnet-session-view-icon--classic' not in rail
    assert 'aria-label="Switch to dark mode"' in rail
    assert ".tailnet-app-controls" in CSS
    assert "tailnetThemeToggle" in JS
    assert "window._pickTheme" in JS
    assert "postMessage(" in JS
    assert "{type:'hermesui:theme',theme:resolvedTheme()}" in JS


def test_cron_notification_rows_are_compact_full_row_disclosures():
    assert "const role=document.createElement('span')" in JS
    assert "const icon=document.createElement('span')" in JS
    assert "button.append(role,response)" in JS
    assert "article.append(button,rich)" in JS
    assert ".tailnet-notification{position:relative;padding:0" in CSS
    assert "grid-template-columns:minmax(0,1fr) auto" in CSS
    assert "min-height:62px" in CSS
    assert ".tailnet-notifications-mode-button,.tailnet-notifications-filter,.tailnet-notifications-read-all,.tailnet-notifications-action,.tailnet-scheduled-action,.tailnet-notification-thread-back,.tailnet-notification-thread-send,.tailnet-notification-thread-stop{min-height:44px;}" in CSS
    assert ".tailnet-notification-toggle{min-height:64px" in CSS


def test_cron_notifications_reuse_existing_frontend_apis_only():
    assert "fetchCronNotificationJobs" in JS
    assert "fetchCronNotificationOutputs" in JS
    assert "mapWithConcurrency(selected,4" in JS
    assert "/apps/api/notifications" not in JS
    assert "indexedDB" not in JS
    assert "CacheStorage" not in JS
    assert "id!==NOTIFICATIONS_ID" in MANAGER


def test_app_selector_is_private_only_without_category_labels():
    rail = _rail_markup()
    assert 'tailnet-app-group-badge' not in rail
    assert '>PRIVATE<' not in rail
    assert '>WORK<' not in rail
    assert '>WEB<' not in rail
    assert 'id="tailnetPrivateAdd"' in rail
    assert 'id="tailnetCompanyAdd"' not in rail
    assert 'id="tailnetPublicAdd"' not in rail
    assert 'id="tailnetCompanyAppLinks"' not in rail
    assert 'id="tailnetPublicAppLinks"' not in rail
    links = rail.index('id="tailnetAppLinks"')
    manager = rail.index('id="tailnetPrivateManager"')
    marketplace = rail.index('id="tailnetPrivateAdd"')
    assert links < manager < marketplace


def test_work_and_web_bookmark_code_is_not_initialized_by_the_private_only_rail():
    load = JS[JS.index("async function loadApps()"):JS.index("\n  loadApps();")]
    assert "companyAdd.addEventListener" not in load
    assert "publicAdd.addEventListener" not in load
    assert "renderSavedGroup('company')" not in load
    assert "renderSavedGroup('public')" not in load
    assert "hydrateSavedGroups()" not in load
    assert "scope:'private-only'" in load
    assert "const BOOKMARK_STORAGE_KEY='hermesui.app-selector.bookmarks.v1'" in JS
    assert "const BOOKMARK_API_PATH='/apps/api/bookmarks'" in JS
    assert "localStorage.getItem(BOOKMARK_STORAGE_KEY)" in JS
    assert "localStorage.setItem(BOOKMARK_STORAGE_KEY" in JS
    assert "method:'PUT'" in JS
    assert "credentials:'same-origin'" in JS
    assert "baseRevision:bookmarkRevision" in JS
    assert "if(!record.initialized&&savedBookmarkCount(savedGroups)>0)" in JS
    assert "if(error&&error.status===409)record=await fetchBookmarkRecord()" in JS
    assert "if(record.initialized)installSavedGroups(record.groups)" in JS
    assert "if(!await ensureBookmarkSync())return" in JS
    assert "showPromptDialog" in JS

    assert "link.dataset.bookmarkGroup=group" in JS
    bookmark_renderer = JS[JS.index("function renderBookmark"):JS.index("function containerForGroup")]
    assert "document.createElement('button')" in bookmark_renderer
    assert "activateBookmark(app)" in bookmark_renderer
    assert "bindBookmarkActions(link)" in bookmark_renderer
    assert "link.setAttribute('aria-haspopup','menu')" in bookmark_renderer
    assert "FRAME_DECISION_STORAGE_KEY" in JS
    assert "FRAME_CHECK_PATH='/frame-check/'" in JS
    assert "const BROWSER_FALLBACK_DELAY_MS=3000" in JS
    assert "window.open(href,'_blank',features)" in JS
    assert "popup=yes" in JS
    assert "Not supported here" not in FRAME_BRIDGE
    assert "Opening in your browser in " in FRAME_BRIDGE


def test_browser_only_frame_decisions_are_rechecked_after_checker_cache_window():
    assert "const FRAME_INLINE_DECISION_TTL_MS=6*60*60*1000" in JS
    assert "const FRAME_BROWSER_DECISION_TTL_MS=5*60*1000" in JS
    fresh = JS[JS.index("function freshFrameDecision"):JS.index("async function refreshFrameDecision")]
    assert "decision.mode==='browser'?FRAME_BROWSER_DECISION_TTL_MS:FRAME_INLINE_DECISION_TTL_MS" in fresh

    node = shutil.which("node")
    assert node, "Node.js is required for the frame-decision cache contract test"
    constants = "\n".join(
        line.strip()
        for line in JS.splitlines()
        if line.strip().startswith("const FRAME_") and "DECISION_TTL_MS=" in line
    )
    harness = f"""
{constants}
let now=1_800_000_000_000;
Date.now=()=>now;
let frameDecisions={{}};
{fresh}
function probe(mode,age){{
  frameDecisions={{'https://app.example/':{{mode,reason:'fixture',checkedAt:now-age}}}};
  return freshFrameDecision('https://app.example/');
}}
process.stdout.write(JSON.stringify({{
  browserFresh:probe('browser',4*60*1000),
  browserExpired:probe('browser',5*60*1000+1),
  inlineFresh:probe('inline',5*60*60*1000),
  inlineExpired:probe('inline',6*60*60*1000+1)
}}));
"""
    proc = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["browserFresh"]["mode"] == "browser"
    assert result["browserExpired"] is None
    assert result["inlineFresh"]["mode"] == "inline"
    assert result["inlineExpired"] is None


def test_saved_bookmark_urls_are_https_only_and_credentials_are_rejected():
    assert "if(!URL_SCHEME_RE.test(value))value=`https://${value}`" in JS
    assert "url.protocol!=='https:'" in JS
    assert "url.username||url.password" in JS
    assert "That address must be a safe HTTPS URL." in JS


def test_group_list_scrolls_inside_the_fixed_rail():
    assert ".rail.tailnet-app-rail{display:flex!important;order:1;position:relative;z-index:240;overflow:hidden;}" in CSS
    assert ".tailnet-app-groups{width:100%;min-height:0;flex:1 1 auto;" in CSS
    assert "overflow-y:auto" in CSS[CSS.index(".tailnet-app-groups{"):CSS.index("}", CSS.index(".tailnet-app-groups{"))]
    assert ".tailnet-app-primary{width:100%;display:flex;flex-direction:column" in CSS


def test_private_app_inventory_is_local_config_not_public_source():
    assert "tailnet-apps.json" not in JS
    assert "const PRIVATE_APPS_PATH='/apps/api/private-apps'" in MANAGER
    assert "credentials:'same-origin'" in MANAGER
    assert "static/tailnet-apps.json" in GITIGNORE.splitlines()
    assert ".ts.net" not in INDEX
    assert ".ts.net" not in JS


def test_private_apps_stay_in_shell_and_only_work_web_use_browser_fallback():
    assert "link.addEventListener('click'" in JS
    assert "activateApp(app)" in JS
    assert "activateBookmark(app)" in JS
    assert "privateAdd.addEventListener('click',()=>activateApp(privateMarketplace))" in JS
    fallback = JS[JS.index("function activateBrowserFallback"):JS.index("function activateBookmark")]
    assert "const shouldOpen=open&&(!alreadyShowing||reopen)" in fallback
    assert "if(!alreadyShowing||reopen)frame.src=app.browserHref" in fallback
    assert "if(shouldOpen)scheduleBrowserFallback(app)" in fallback
    activation = JS[JS.index("function activateBookmark"):JS.index("function appIcon")]
    assert "activateBrowserFallback(app,{reopen:true})" in activation
    assert "if(activeId===app.id&&frame.dataset.browserFallback!=='true')" in activation
    assert "reserveBrowserTab" not in activation
    assert "function activateBrowserFallback(app,{open=true,reopen=false}={})" in JS
    assert "cancelBrowserFallback();" in fallback
    assert "BROWSER_FALLBACK_DELAY_MS" in JS[JS.index("function scheduleBrowserFallback"):JS.index("function activateBrowserFallback")]
    assert "refreshFrameDecision(app).then" not in activation
    assert "reservedBrowserTabs" not in JS
    assert "browserReservationHref" not in JS
    message_handler = JS[JS.index("window.addEventListener('message'"):JS.index("document.addEventListener('pointerover'")]
    assert "takeReservedTab" not in message_handler
    assert "if(data.mode==='browser')activateBrowserFallback(app)" in message_handler
    private_activation = MANAGER[MANAGER.index("function openPrivateApp"):MANAGER.index("function renderApprovedApps")]
    assert "frame.src=app.frameHref" in private_activation
    assert "activateBrowserFallback" not in private_activation
    assert "button.dataset.tailnetAppId=app.id" in MANAGER
    assert "href.origin!==location.origin" in MANAGER
    assert "frameHref.origin!==location.origin" in MANAGER


def test_marketplace_storefront_is_the_ai_wizards_panel_app_library():
    rail = _rail_markup()
    assert 'aria-label="Marketplace"' in rail
    assert 'data-tooltip="Marketplace"' in rail
    assert '<path d="M4 10h16l-2-6H6z"/>' in rail
    assert '<span aria-hidden="true">+</span>' not in rail
    assert "id:'private-marketplace'" in JS
    assert "href:'https://www.aiwizards.com/apps'" in JS
    assert "frameHref:new URL('/tailnet-frame/?app=private-marketplace&library=aiwizards-v2',location.origin).href" in JS
    assert "?'app:private-marketplace:aiwizards-v2'" in JS
    assert "privateAdd.addEventListener('click',()=>activateApp(privateMarketplace))" in JS
    assert "if(id==='private-marketplace')return {label:'Private app library',href:'https://www.aiwizards.com/apps'}" in FRAME_BRIDGE


def test_same_origin_frame_bridge_resolves_only_valid_saved_work_and_web_entries():
    assert "const GROUPS=new Set(['company','public'])" in FRAME_BRIDGE
    assert "const BOOKMARK_API_PATH='/apps/api/bookmarks'" in FRAME_BRIDGE
    assert "credentials:'same-origin'" in FRAME_BRIDGE
    assert "payload&&payload.ok===true&&payload.version===1&&payload.initialized===true" in FRAME_BRIDGE
    assert "localStorage.getItem(BOOKMARK_STORAGE_KEY)" in FRAME_BRIDGE
    assert "payload.version!==1" in FRAME_BRIDGE
    assert "url.protocol!=='https:'||url.username||url.password" in FRAME_BRIDGE
    assert "return cleanDestination(entries.find(item=>item&&item.id===id))" in FRAME_BRIDGE
    assert "if(browserToken)app=await readBookmark(browserToken)" in FRAME_BRIDGE
    assert "frame.src=app.href" in FRAME_BRIDGE
    assert "target=\"_blank\"" in FRAME_BRIDGE
    assert "rel=\"noopener noreferrer\"" in FRAME_BRIDGE
    assert "window.open(" not in FRAME_BRIDGE
    assert "vnc_auto" not in FRAME_BRIDGE
    assert "websockify" not in FRAME_BRIDGE
    assert "openInTailnetBrowser" not in FRAME_BRIDGE
    assert "fetch('./navigate'" not in FRAME_BRIDGE
    assert "?bookmark=${encodeURIComponent(`${group}:${id}`)}" in JS
    assert "?browser=${encodeURIComponent(`${group}:${id}`)}" in JS
    assert "hermesui:bookmark-frame-decision" in JS
    assert "hermesui:bookmark-frame-decision" in FRAME_BRIDGE
    assert "notifyParent(bookmarkToken,'unknown'" in FRAME_BRIDGE
    assert "notifyParent(bookmarkToken,'inline'" in FRAME_BRIDGE
    assert 'id="manualBrowserAction"' in FRAME_BRIDGE
    assert "if(!decision||decision.mode==='unknown')" in FRAME_BRIDGE
    assert "manualAction.href=app.href" in FRAME_BRIDGE
    assert "!['inline','browser','unknown'].includes(payload.mode)" in FRAME_BRIDGE
    assert "const generation=params.get('generation')||''" in FRAME_BRIDGE
    assert "generation," in FRAME_BRIDGE
    assert "url.searchParams.set('generation',generation)" in JS


def test_bookmark_frame_decisions_are_bound_to_the_current_navigation_generation():
    node = shutil.which("node")
    assert node, "Node.js is required for the bookmark navigation-generation contract test"
    token_start = JS.index("  function bookmarkToken(app){")
    token_end = JS.index("\n  function nextBookmarkGeneration", token_start)
    current_start = JS.index("  function isCurrentBookmarkDecision(data,app){")
    current_end = JS.index("\n  function emptySavedGroups", current_start)
    source = JS[token_start:token_end] + "\n" + JS[current_start:current_end]
    harness = f"""
const GROUPS={{company:{{}},public:{{}}}};
let activeId='shared';
let activeBookmarkNavigation={{token:'company:shared',generation:'3'}};
{source}
const app={{id:'shared',group:'company'}};
process.stdout.write(JSON.stringify({{
  current:isCurrentBookmarkDecision({{token:'company:shared',generation:'3'}},app),
  staleGeneration:isCurrentBookmarkDecision({{token:'company:shared',generation:'1'}},app),
  wrongToken:isCurrentBookmarkDecision({{token:'public:shared',generation:'3'}},app),
  inactive:(()=>{{activeId='other';return isCurrentBookmarkDecision({{token:'company:shared',generation:'3'}},app);}})()
}}));
"""
    proc = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {
        "current": True,
        "staleGeneration": False,
        "wrongToken": False,
        "inactive": False,
    }

    handler = JS[JS.index("window.addEventListener('message'"):JS.index("document.addEventListener('pointerover'")]
    current_check = handler.index("if(!isCurrentBookmarkDecision(data,app))return")
    cache_write = handler.index("frameDecisions[app.href]")
    fallback = handler.index("activateBrowserFallback(app)")
    assert current_check < cache_write < fallback
    assert "typeof data.generation!=='string'" in handler


def test_work_web_links_do_not_preopen_a_browser_before_inline_decision():
    activation = JS[JS.index("function activateBookmark"):JS.index("function appIcon")]
    assert "window.open" not in activation
    assert "reserve" not in activation.lower()
    assert "activateApp(app,{bookmarkGeneration:generation})" in activation
    assert "decision&&decision.mode==='browser'" in activation
    assert "activateBrowserFallback(app,{reopen:true})" in activation
    assert "bookmark-fallback=v5&bookmark-sync=v1" in INDEX
    assert "bookmark-fallback=v5&bookmark-sync=v1" in (ROOT / "static" / "sw.js").read_text(encoding="utf-8")


def test_browser_fallback_countdown_is_delayed_cancellable_and_accessible():
    schedule = JS[JS.index("function scheduleBrowserFallback"):JS.index("function activateBrowserFallback")]
    assert "window.setTimeout" in schedule
    assert "BROWSER_FALLBACK_DELAY_MS" in schedule
    assert "openBrowserWindow(app.href)" in schedule
    assert "frame.dataset.browserFallback!=='true'" in schedule
    assert "type:'hermesui:bookmark-browser-result'" in JS
    assert "cancelBrowserFallback();\n    hideTooltip();" in JS
    assert "cancelBrowserFallback();\n    const token=bookmarkToken(app);" in JS
    assert 'aria-live="assertive"' in FRAME_BRIDGE
    assert "let remaining=3" in FRAME_BRIDGE
    assert "fallbackCountdownTimer=setTimeout(tick,1000)" in FRAME_BRIDGE
    assert "copy.hidden=true" in FRAME_BRIDGE
    assert "Opening in your browser in " in FRAME_BRIDGE
    assert "action.hidden=true" in FRAME_BRIDGE
    assert "title.textContent='Open in browser'" in FRAME_BRIDGE
    assert "This site doesn’t support opening inside Hermes." in FRAME_BRIDGE
    assert "title.textContent=payload.opened?'Opened in browser':'Open in browser'" in FRAME_BRIDGE
    assert 'font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,system-ui,sans-serif' in FRAME_BRIDGE


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


def test_documented_app_entry_normalizes_to_canonical_direct_and_embedded_destinations():
    assert "only canonical app paths on HermesUI's own default Tailnet origin" in README
    app = _clean_app(
        {
            "id": "private-app",
            "label": "Private App",
            "sourceKey": "route-key",
            "href": "https://host.example/private-app/",
            "frameHref": "https://host.example/private-app/",
            "icon": "apps",
        }
    )
    assert app == {
        "id": "private-app",
        "label": "Private App",
        "sourceKey": "route-key",
        "href": "https://host.example/private-app/",
        "frameHref": "https://host.example/private-app/",
        "icon": "apps",
    }
    assert "frame.src=app.frameHref" in MANAGER


def test_required_app_urls_are_rejected_before_url_coercion():
    valid = {
        "id": "private-app",
        "label": "Private App",
        "sourceKey": "route-key",
        "href": "https://host.example:9443/private-app/",
        "frameHref": "https://host.example:9443/private-app/",
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


def test_mobile_app_selector_is_fixed_on_the_right_and_sessions_are_a_real_page():
    assert (
        '.rail.tailnet-app-rail{position:fixed;left:auto;right:0;top:0;bottom:0;width:48px;'
        'height:100%;height:100dvh;box-sizing:border-box;'
        in CSS
    )
    assert '.layout{margin-left:0;margin-right:48px;width:calc(100% - 48px);}' in CSS
    assert (
        'html:not([data-tailnet-view="external"]) .app-titlebar{'
        'margin-left:0;margin-right:48px;width:calc(100% - 48px);box-sizing:border-box;}'
        in CSS
    )
    assert (
        'html:not([data-tailnet-view="external"]) .sidebar{left:0;right:auto;'
        'width:calc(100vw - 48px);transform:translateX(-100%);}'
        in CSS
    )
    assert (
        'html:not([data-tailnet-view="external"]) .sidebar.mobile-open{'
        'transform:translateX(0);}'
        in CSS
    )
    assert 'id="btnHamburger"' not in INDEX
    assert 'id="mobileSessionTabs"' in INDEX
    assert "activateHermes({openMobileMenu:true})" in JS
    assert "function openMobileSessionPage()" in BOOT
    assert "openMobileSessionPage();" in BOOT
    assert "document.documentElement.dataset.mobileSessionView='sessions';" in BOOT
    assert "if(_mobileSessionSelectionRequired())return openMobileSessionPage();" in BOOT
    assert "if(typeof openMobileSessionPage==='function') openMobileSessionPage();" in BOOT
    assert "if(typeof syncMobileSessionNavigation==='function') syncMobileSessionNavigation();" in SWIPE
    assert 'html[data-mobile-session-view="sessions"] .app-titlebar{display:none!important;}' in CSS
    assert '.sidebar.mobile-session-page .mobile-sidebar-close{display:none!important;}' in CSS
    assert '.sidebar.mobile-session-page .panel-view{margin-left:0;}' in CSS
    assert '.rail.tailnet-app-rail{border-right:0;border-left:1px solid var(--border);}' in CSS
    assert '.rail.tailnet-app-rail .rail-btn.active{color:var(--accent);background:color-mix(in srgb,var(--accent) 10%,transparent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--accent) 55%,transparent);}' in CSS
    assert '.rail.tailnet-app-rail .rail-btn.active::before' not in CSS
    assert '.rail .nav-tab.active::before' not in CSS
    assert '.rail.tailnet-app-rail .rail-btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}' in CSS
    assert '.tailnet-scheduled-job-menu{position:fixed;z-index:100;top:auto;right:60px;' in CSS
    assert '.toast{right:60px;left:12px;' in CSS


def test_rail_tooltips_and_bookmark_actions_flip_away_from_the_right_edge():
    assert "const placeLeft=rect.left>window.innerWidth/2;" in JS
    assert "placeLeft?rect.left-width-8:rect.right+8" in JS
    assert "anchorX>window.innerWidth/2" in JS


def test_mobile_hermes_home_becomes_a_session_menu_only_outside_the_session_list():
    rail = _rail_markup()
    assert 'class="tailnet-app-home-icon"' in rail
    assert 'class="tailnet-app-home-menu-icon"' in rail
    assert '<path d="M4 7h16M4 12h16M4 17h16"/>' in rail
    assert "function syncHermesHomeControl()" in JS
    assert "root.dataset.mobileSessionView!=='sessions'" in JS
    assert "home.classList.toggle('is-session-menu',opensSessions)" in JS
    assert "const label=opensSessions?'Open sessions':'Hermes UI'" in JS
    assert "attributeFilter:['data-tailnet-view','data-mobile-session-view']" in JS
    assert '#tailnetAppHome.is-session-menu .tailnet-app-home-icon{display:none;}' in CSS
    assert '#tailnetAppHome.is-session-menu .tailnet-app-home-menu-icon{display:flex;}' in CSS


def test_tailnet_rail_script_is_loaded_from_the_mount_aware_base():
    assert (
        'src="static/tailnet-app-rail.js?v=__WEBUI_VERSION__'
        '&overlay=wizard-canvas-v8&bookmark-fallback=v5&bookmark-sync=v1&cron-notifications=v7&shell-theme=v1&private-only=v1&mobile-session-home=v1&cron-operations=v3&mobile-rail-right=v1"'
        in INDEX
    )
    assert (
        'src="static/tailnet-app-manager.js?v=__WEBUI_VERSION__'
        '&cron-notifications=v3&semantic-icons=v1"'
        in INDEX
    )
    assert "new URL(PRIVATE_APPS_PATH,location.origin)" in MANAGER