from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
SW = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
LAYER = (ROOT / "static" / "mobile-layer-navigation.js").read_text(encoding="utf-8")
RAIL = (ROOT / "static" / "tailnet-app-rail.js").read_text(encoding="utf-8")
MANAGER = (ROOT / "static" / "tailnet-app-manager.js").read_text(encoding="utf-8")


def test_mobile_layer_navigation_is_a_separate_cached_shell_asset():
    index_line = next(line for line in INDEX.splitlines() if "static/mobile-layer-navigation.js?v=" in line)
    sw_line = next(line for line in SW.splitlines() if "'./static/mobile-layer-navigation.js' + VQ" in line)
    assert "&mobile-layer-nav=v3" in index_line
    assert "&mobile-layer-nav=v3" in sw_line
    assert 'id="mobileAppLayerSwipeZone"' in INDEX
    assert 'id="mobileLayerBackSwipeZone"' in INDEX
    assert 'id="mobileLayerAnnouncer" aria-live="polite" aria-atomic="true"' in INDEX
    assert "session-swipe-navigation.js" not in INDEX
    assert "session-swipe-navigation.js" not in SW


def test_mobile_layer_order_is_tailnet_sessions_conversation_and_reversible():
    assert "if(layer==='conversation'&&direction==='back')" in LAYER
    assert "tailnet.openSessionsFromConversation()" in LAYER
    assert "openSessionsFromConversation:openMobileSessionsFromConversation" in RAIL
    assert "if(layer==='sessions'&&direction==='forward')" in LAYER
    assert "window.closeMobileSidebar(true);" in LAYER
    assert "if(layer==='sessions'&&direction==='back')" in LAYER
    assert "tailnet.restoreLastApp()" in LAYER
    assert "if(layer==='app'&&direction==='forward')" in LAYER
    assert "tailnet.openSessions()" in LAYER
    assert "if(root.dataset.tailnetView==='external')return 'app';" in LAYER
    assert "if(root.dataset.mobileSessionView==='sessions')return 'sessions';" in LAYER


def test_layer_swipes_are_edge_only_axis_locked_and_do_not_own_horizontal_content():
    for contract in (
        "const BACK_EDGE_WIDTH_PX=40;",
        "const EDGE_INSET_PX=16;",
        "const EDGE_WIDTH_PX=24;",
        "const AXIS_LOCK_PX=10;",
        "const ACTIVATE_PX=24;",
        "const COMMIT_PX=72;",
        "const FLICK_DISTANCE_PX=40;",
        "const FLICK_VELOCITY_PX_MS=.5;",
        "const DOMINANCE_RATIO=1.6;",
        "const GESTURE_TIMEOUT_MS=900;",
        "const COOLDOWN_MS=250;",
    ):
        assert contract in LAYER
    assert "touch.clientX>=0&&touch.clientX<=BACK_EDGE_WIDTH_PX" in LAYER
    assert "layer==='conversation'&&target===backSwipeZone&&inBackBand" in LAYER
    for protected in (
        ".composer-box",
        ".messages pre",
        "table",
        ".project-bar",
        ".session-source-tabs",
        ".mobile-primary-menu",
        ".rightpanel",
        "[role=\"dialog\"]",
    ):
        assert protected in LAYER
    assert "cancelOriginRow();" in LAYER
    assert "event.preventDefault();" in LAYER
    assert "event.stopImmediatePropagation();" in LAYER
    assert "html,body{overscroll-behavior:none;}" in CSS


def test_tailnet_layer_restores_the_last_real_app_without_forgetting_its_frame():
    assert "const MOBILE_LAST_APP_STORAGE_KEY='hermesui.tailnet.last-app.v1';" in RAIL
    assert "lastMobileAppSnapshot={id,token:String(token||''),generation:String(generation||''),browserFallback:!!browserFallback};" in RAIL
    assert "activateHermes({remember:false});" in RAIL
    assert "restoreLastApp:restoreLastMobileTailnetApp" in RAIL
    assert "openSessions:openMobileSessionsFromTailnet" in RAIL
    assert "closeUtilities:closeMobileUtilitiesForLayerGesture" in RAIL
    assert "window.hermesTailnetManagerRestoreApp(id)===true" in RAIL
    assert "sessionStorage.setItem(MOBILE_LAST_APP_STORAGE_KEY,app.id);" in MANAGER
    assert "window.hermesTailnetManagerRestoreApp=restoreManagedTailnetApp;" in MANAGER


def test_nested_mobile_surfaces_consume_the_first_layer_gesture():
    assert "node.getClientRects().length>0" in LAYER
    assert "utilitiesOpenAtPointerDown" in LAYER
    assert "if(finished.consumeUtilities)return;" in LAYER
    assert "if(activeId===NOTIFICATIONS_ID&&notificationThreadItem)" in RAIL
    assert "closeNotificationThread();\n      return false;" in RAIL


def test_compact_titlebar_only_occupies_the_mobile_conversation_layer():
    phone = CSS[CSS.index("@media(max-width:640px)"):]
    assert ".app-titlebar{display:flex!important;height:34px" in phone
    assert ".app-titlebar-title{max-width:100%;min-width:0;font-size:13.5px;font-weight:650" in phone
    assert 'html[data-mobile-session-view="sessions"] .app-titlebar,html[data-tailnet-view="external"] .app-titlebar{display:none!important;}' in phone
    assert ".app-titlebar-icon,.app-titlebar-sub,.app-titlebar-spacer,.app-titlebar-reload" in phone
    assert "document.getElementById('appTitlebarTitle').setAttribute('tabindex','-1')" in LAYER
    assert "Conversation${title&&title.textContent?` — ${title.textContent.trim()}`:''}" in LAYER


def test_app_iframe_has_a_narrow_parent_owned_forward_swipe_zone():
    assert 'html[data-tailnet-view="external"] .mobile-app-layer-swipe-zone{' in CSS
    assert "right:calc(var(--mobile-rail-w) + 16px)" in CSS
    assert "width:24px" in CSS
    assert "touch-action:pan-y" in CSS
    assert "if(target!==appSwipeZone)return null;" in LAYER
    assert "return {layer,direction:'forward',sign:-1};" in LAYER


def test_conversation_has_a_parent_owned_physical_edge_swipe_zone():
    assert 'html[data-mobile-layer="conversation"] .mobile-layer-back-swipe-zone{' in CSS
    assert "left:0" in CSS
    assert "width:40px" in CSS
    assert "touch-action:pan-y" in CSS
    assert "target===backSwipeZone||target===appSwipeZone" in LAYER


def test_conversation_back_swipe_presses_sessions_once_before_touchend():
    assert "const CONVERSATION_COMMIT_PX=24;" in LAYER
    assert "committed:false" in LAYER
    assert "if(gesture&&gesture.committed){" in LAYER
    assert "gesture.layer==='conversation'&&gesture.direction==='back'" in LAYER
    assert "gesture.committed=true;" in LAYER
    assert "navigate(gesture.direction,{fromGesture:true});" in LAYER
    assert "if(finished.committed){" in LAYER


def test_layer_navigation_cache_identities_match_index_and_worker():
    for token in ("&mobile-folder-quiet=v2", "&mobile-titlebar=v1", "&mobile-layer-nav=v3"):
        assert token in next(line for line in INDEX.splitlines() if "static/style.css?v=" in line)
        assert token in next(line for line in SW.splitlines() if "'./static/style.css' + VQ" in line)
    for asset in ("tailnet-app-rail.js", "tailnet-app-manager.js"):
        index_line = next(line for line in INDEX.splitlines() if f"static/{asset}?v=" in line)
        sw_line = next(line for line in SW.splitlines() if f"'./static/{asset}' + VQ" in line)
        assert "&mobile-layer-nav=v3" in index_line
        assert "&mobile-layer-nav=v3" in sw_line
