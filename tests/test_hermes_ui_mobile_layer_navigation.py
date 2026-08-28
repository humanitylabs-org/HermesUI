from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
SW = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
LAYER = (ROOT / "static" / "mobile-layer-navigation.js").read_text(encoding="utf-8")
RAIL = (ROOT / "static" / "tailnet-app-rail.js").read_text(encoding="utf-8")
MANAGER = (ROOT / "static" / "tailnet-app-manager.js").read_text(encoding="utf-8")
SESSIONS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
BOOT = (ROOT / "static" / "boot.js").read_text(encoding="utf-8")


def test_mobile_layer_navigation_is_a_separate_cached_shell_asset():
    index_line = next(line for line in INDEX.splitlines() if "static/mobile-layer-navigation.js?v=" in line)
    sw_line = next(line for line in SW.splitlines() if "'./static/mobile-layer-navigation.js' + VQ" in line)
    assert "&mobile-layer-nav=v8" in index_line
    assert "&mobile-layer-nav=v8" in sw_line
    assert 'id="mobileAppLayerSwipeZone"' in INDEX
    assert 'id="mobileLayerBackSwipeZone"' in INDEX
    assert 'id="mobileLayerAnnouncer" aria-live="polite" aria-atomic="true"' in INDEX
    assert "session-swipe-navigation.js" not in INDEX
    assert "session-swipe-navigation.js" not in SW
    assert not (ROOT / "static" / "session-swipe-navigation.js").exists()


def test_mobile_hierarchy_is_forward_by_tap_and_back_only_by_gesture():
    assert "if(layer==='conversation'&&direction==='back')" in LAYER
    assert "tailnet.openSessionsFromConversation()" in LAYER
    assert "if(layer==='app'&&direction==='back')" in LAYER
    assert "tailnet.openConversation()" in LAYER
    assert "tailnet.openSessions()" in LAYER
    assert "openSessionsFromConversation:openMobileSessionsFromConversation" in RAIL
    assert "openConversation:openMobileConversationFromTailnet" in RAIL
    assert "openSessions:openMobileSessionsFromTailnet" in RAIL
    assert "direction==='forward'" not in LAYER
    assert "sessions-to-conversation" not in LAYER
    assert "conversation-to-app" not in LAYER
    assert "if(root.dataset.tailnetView==='external')return 'app';" in LAYER
    assert "if(root.dataset.mobileSessionView==='sessions')return 'sessions';" in LAYER


def test_back_swipe_is_left_edge_only_and_axis_locked():
    for contract in (
        "const BACK_EDGE_WIDTH_PX=24;",
        "const AXIS_LOCK_PX=10;",
        "const INTERACTIVE_COMMIT_RATIO=.34;",
        "const INTERACTIVE_FLICK_MIN_PX=28;",
        "const INTERACTIVE_FLICK_VELOCITY_PX_MS=.35;",
        "const INTERACTIVE_REVERSE_VELOCITY_PX_MS=.35;",
        "const DOMINANCE_RATIO=1.6;",
    ):
        assert contract in LAYER
    assert "const inBackBand=touch.clientX>=0&&touch.clientX<=BACK_EDGE_WIDTH_PX;" in LAYER
    assert "if(layer==='conversation'&&target===backSwipeZone){" in LAYER
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
    assert "event.preventDefault();" in LAYER
    assert "event.stopImmediatePropagation();" in LAYER
    assert "html,body{overscroll-behavior:none;}" in CSS


def test_tailnet_back_restores_the_live_parent_without_reloading_the_frame():
    assert "const MOBILE_LAST_APP_STORAGE_KEY='hermesui.tailnet.last-app.v1';" in RAIL
    assert "activateHermes({remember:false});" in RAIL
    assert "canLeaveActiveApp:canLeaveActiveMobileTailnetApp" in RAIL
    assert "sessionStorage.setItem(MOBILE_LAST_APP_STORAGE_KEY,app.id);" in MANAGER
    assert "window.hermesTailnetManagerRestoreApp=restoreManagedTailnetApp;" in MANAGER
    assert "dragMode:hasConversation()?'app-to-conversation':'app-to-sessions'" in LAYER
    assert "if(frame.dataset.tailnetFrameKey!==frameKey||wasBrowserFallback)" in RAIL
    assert "restoreLastMobileTailnetApp" not in RAIL
    assert "canPreviewLastMobileTailnetApp" not in RAIL


def test_nested_mobile_surfaces_consume_the_first_gesture_without_animating():
    assert "node.getClientRects().length>0" in LAYER
    assert "tailnet.closeUtilities()" in LAYER
    assert "utilitiesOpenAtPointerDown" not in LAYER
    assert "consumeUtilities" not in LAYER
    assert "if(activeId===NOTIFICATIONS_ID&&notificationThreadItem)" in RAIL
    assert "closeNotificationThread();\n      return false;" in RAIL


def test_compact_titlebar_only_occupies_the_mobile_conversation_layer():
    phone = CSS[CSS.index("@media(max-width:640px)"):]
    assert ".app-titlebar{display:flex!important;height:34px" in phone
    assert ".app-titlebar-title{max-width:100%;min-width:0;font-size:13.5px;font-weight:650" in phone
    assert 'html[data-mobile-session-view="sessions"] .app-titlebar,html[data-tailnet-view="external"] .app-titlebar{display:none!important;}' in phone
    assert ".app-titlebar-icon,.app-titlebar-sub,.app-titlebar-spacer,.app-titlebar-reload" in phone
    assert "document.getElementById('appTitlebarTitle').setAttribute('tabindex','-1')" in LAYER


def test_each_live_surface_has_one_narrow_back_edge_zone():
    assert 'html[data-mobile-layer="conversation"] .mobile-layer-back-swipe-zone,' in CSS
    assert 'html[data-tailnet-view="external"] .mobile-app-layer-swipe-zone{' in CSS
    assert 'html[data-mobile-layer="conversation"] .mobile-layer-back-swipe-zone{width:24px;}' in CSS
    assert 'html[data-tailnet-view="external"] .mobile-app-layer-swipe-zone{width:40px;}' in CSS
    assert "touch-action:pan-y" in CSS
    assert "if(layer==='conversation'&&target===backSwipeZone)" in LAYER
    assert "if(target!==appSwipeZone)return null;" in LAYER
    assert "if(target===backSwipeZone||target===appSwipeZone)return false;" in LAYER


def test_only_the_outgoing_card_tracks_the_thumb_over_a_stationary_parent():
    assert "interactive:true,dragMode:'conversation-to-sessions'" in LAYER
    assert "dragMode:hasConversation()?'app-to-conversation':'app-to-sessions'" in LAYER
    assert "const offset=Math.max(0,Math.min(width,dx));" in LAYER
    assert "const progress=Math.max(0,Math.min(1,offset/width));" in LAYER
    assert "root.style.setProperty('--mobile-layer-drag-offset',`${offset}px`)" in LAYER
    assert "--mobile-layer-drag-parallax" not in LAYER
    assert "--mobile-layer-drag-parallax" not in CSS
    assert "--mobile-layer-drag-progress" not in LAYER
    assert "distance>=width*INTERACTIVE_COMMIT_RATIO" in LAYER
    assert "const reverseFling=velocity<=-INTERACTIVE_REVERSE_VELOCITY_PX_MS;" in LAYER
    assert 'html[data-mobile-layer-drag="conversation-to-sessions"] .sidebar' in CSS
    assert "translate3d(calc(-30%" not in CSS
    assert 'html[data-mobile-layer-drag="conversation-to-sessions"] .sidebar{display:flex!important;z-index:200;transform:none;' in CSS
    assert 'html[data-mobile-layer-drag="conversation-to-sessions"] .layout>.main' in CSS
    assert 'html[data-mobile-layer-drag="conversation-to-sessions"] .app-titlebar' in CSS
    assert 'html[data-mobile-layer-drag="app-to-conversation"] .tailnet-app-workspace' in CSS
    assert 'html[data-mobile-layer-drag="app-to-sessions"] .tailnet-app-workspace' in CSS
    assert "translate3d(var(--mobile-layer-drag-offset,0px),0,0)" in CSS
    assert '#tailnetAppFrame{pointer-events:none;}' in CSS
    assert 'data-mobile-layer-drag="sessions-to-conversation"' not in CSS
    assert 'data-mobile-layer-drag="conversation-to-app"' not in CSS
    assert "window.switchPanel('chat')" not in LAYER
    assert "__sessionSwipeNavigation" not in LAYER


def test_back_gesture_previews_the_exact_sessions_page_used_by_the_button():
    assert "function markDragPreview()" in LAYER
    assert "function clearDragPreview()" in LAYER
    assert "sidebar.dataset.mobileLayerPreview='sessions';" in LAYER
    assert "sidebar.classList.add('mobile-session-page');" in LAYER
    assert "if(root.dataset.mobileSessionView!=='sessions')sidebar.classList.remove('mobile-session-page');" in LAYER
    assert "const entering=document.documentElement.dataset.mobileSessionView!=='sessions';" in BOOT
    assert "window.switchPanel('chat')" not in LAYER


def test_interactive_back_swipe_settles_once_and_respects_reduced_motion():
    assert "root.dataset.mobileLayerBusy='true';" in LAYER
    assert "root.removeAttribute('data-mobile-layer-busy');" in LAYER
    assert "if(commits)suppressClickUntil=Date.now()+250;" in LAYER
    assert "Date.now()>=suppressClickUntil" in LAYER
    assert "window.matchMedia('(prefers-reduced-motion:reduce)').matches" in LAYER
    assert 'html[data-mobile-layer-drag-phase="settling"] .sidebar' not in CSS
    assert 'html[data-mobile-layer-drag-phase="settling"] .layout>.main' in CSS
    assert 'transition-duration:.01ms!important;' in CSS
    assert "pointerId," in LAYER
    assert "if(!gesture||gesture.releasing)return;" in LAYER
    assert "function onPointerRelease(event)" in LAYER
    assert "function onTouchEnd(event)" in LAYER
    assert LAYER.count("finishGestureAt(gesture.lastX,gesture.lastY,event);") == 2


def test_back_swipe_fails_closed_and_cleans_up_on_interruptions():
    assert "if(event.touches.length!==1)onTouchCancel(null);" in LAYER
    assert "window.addEventListener('resize',()=>{clearInteractiveDrag();resetGesture();syncLayer();}" in LAYER
    assert "document.addEventListener('hermesui:tailnet-app-selected',()=>{clearInteractiveDrag();resetGesture();syncLayer();});" in LAYER
    assert "attributeFilter:['data-tailnet-view','data-mobile-session-view']" in LAYER
    observer_tail = LAYER[LAYER.index("attributeFilter:"):]
    assert "data-mobile-rail" not in observer_tail


def test_session_loading_skeleton_never_repaints_mid_back_gesture():
    assert "const _SESSION_CONTENT_LOADING_SHOW_DELAY_MS=120;" in SESSIONS
    assert "const _SESSION_CONTENT_LOADING_MIN_VISIBLE_MS=320;" in SESSIONS
    assert "if(document.documentElement.hasAttribute('data-mobile-layer-drag'))" in SESSIONS
    assert "_scheduleSessionContentLoadingShow(60);" in SESSIONS
    assert "document.addEventListener('hermesui:mobile-layer-change'" not in SESSIONS
    assert "if(conversationIsLoading())return null;" in LAYER
    assert ".session-switch-skeleton" in CSS
    assert "data-mobile-session-loading" not in CSS


def test_layer_navigation_cache_identities_match_index_and_worker():
    for token in ("&mobile-folder-quiet=v2", "&mobile-titlebar=v1", "&mobile-layer-nav=v7"):
        assert token in next(line for line in INDEX.splitlines() if "static/style.css?v=" in line)
        assert token in next(line for line in SW.splitlines() if "'./static/style.css' + VQ" in line)
    sessions_index = next(line for line in INDEX.splitlines() if "static/sessions.js?v=" in line)
    sessions_sw = next(line for line in SW.splitlines() if "'./static/sessions.js' + VQ" in line)
    assert "&mobile-back-loading=v3" in sessions_index
    assert "&mobile-back-loading=v3" in sessions_sw
    boot_index = next(line for line in INDEX.splitlines() if "static/boot.js?v=" in line)
    boot_sw = next(line for line in SW.splitlines() if "'./static/boot.js' + VQ" in line)
    assert "&mobile-back-instant=v1" in boot_index
    assert "&mobile-back-instant=v1" in boot_sw
    for asset, token in (("tailnet-app-rail.js", "v5"), ("tailnet-app-manager.js", "v3")):
        index_line = next(line for line in INDEX.splitlines() if f"static/{asset}?v=" in line)
        sw_line = next(line for line in SW.splitlines() if f"'./static/{asset}' + VQ" in line)
        assert f"&mobile-layer-nav={token}" in index_line
        assert f"&mobile-layer-nav={token}" in sw_line
