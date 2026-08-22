from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
SW = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
SWIPE = (ROOT / "static" / "session-swipe-navigation.js").read_text(encoding="utf-8")
SESSIONS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
UI = (ROOT / "static" / "ui.js").read_text(encoding="utf-8")


def test_mobile_session_swipe_is_a_versioned_frontend_shell_asset():
    script = 'static/session-swipe-navigation.js?v=__WEBUI_VERSION__'
    assert f'src="{script}" defer' in INDEX
    assert INDEX.index(script) > INDEX.index('static/sessions.js?v=__WEBUI_VERSION__')
    assert "'./static/session-swipe-navigation.js' + VQ" in SW
    assert "fetch(" not in SWIPE
    assert "/api/" not in SWIPE


def test_swipe_is_phone_and_coarse_pointer_only():
    assert "const PHONE_QUERY='(max-width: 640px)'" in SWIPE
    assert "const COARSE_QUERY='(pointer: coarse)'" in SWIPE
    assert "const enabled=()=>media(PHONE_QUERY)&&media(COARSE_QUERY)" in SWIPE
    assert "if(!enabled()||swipeAnimating||gesture||!currentSid()) return" in SWIPE
    assert "@media (max-width:640px) and (pointer:coarse){.messages-shell{touch-action:pan-y;}}" in CSS


def test_mobile_shell_has_no_swipe_down_refresh_gesture():
    assert "Pull-to-refresh for PWA standalone" not in UI
    assert "pull-to-refresh-indicator" not in UI
    assert "refreshSessionList('pull'" not in UI
    assert "pull-to-refresh-indicator" not in CSS
    assert "html,body{overscroll-behavior-y:none;}" in CSS


def test_swipe_uses_visible_sidebar_order_and_existing_session_switch_path():
    assert "_sessionVisibleSidebarIds" in SWIPE
    assert "const targetSid=ids[index+(direction<0?1:-1)]" in SWIPE
    assert "_allSessions.find" in SWIPE
    assert "_openSidebarSession(target,{source,suppressSessionContentLoading:true})" in SWIPE
    assert "async function openTarget(target,source='mobile-session-swipe')" in SWIPE
    assert "left advances to the next older row" in SWIPE
    assert "right returns to the previous newer row" in SWIPE


def test_swipe_distinguishes_vertical_scroll_snap_and_commit():
    assert "if(absY>absX*1.12){gesture=null;return;}" in SWIPE
    assert "if(event.cancelable) event.preventDefault()" in SWIPE
    assert "const fast=Math.abs(active.velocityX)>=FLICK_VELOCITY&&distance>=FLICK_MIN_DISTANCE" in SWIPE
    assert "const far=distance>=commitDistance()" in SWIPE
    assert "if(!target||(!fast&&!far)){snapBack();return;}" in SWIPE
    assert "await switchTarget(target,'mobile-session-swipe')" in SWIPE
    assert "applySwipeVisual(dx,gesture.target,gesture.direction)" in SWIPE
    assert "Release to open" not in SWIPE


def test_swipe_does_not_start_on_edges_or_interactive_content():
    assert "const EDGE_GUARD=22" in SWIPE
    assert "event.clientX<=EDGE_GUARD||event.clientX>=window.innerWidth-EDGE_GUARD" in SWIPE
    for selector in ("button", "a", "input", "textarea", "pre", "code", ".markdown-table-wrap"):
        assert selector in SWIPE
    assert "event.target.closest(INTERACTIVE_SELECTOR)" in SWIPE
    assert "selection.type==='Range'&&!selection.isCollapsed" in SWIPE


def test_swipe_and_tab_click_share_one_loading_experience():
    assert ".session-swipe-preview{" in CSS
    assert "function ensureSwipePreview()" in SWIPE
    assert "cloneNode(true)" in SWIPE
    assert "preview.setAttribute('aria-hidden','true')" in SWIPE
    assert "void switchTarget(sessionForSid(sid),'mobile-session-tab')" in SWIPE
    assert "await switchTarget(target,'mobile-session-swipe')" in SWIPE
    assert "const loadingToken=beginNavigationLoading()" in SWIPE
    assert "endNavigationLoading(loadingToken)" in SWIPE
    assert "contentLoadingDepth=Math.max(0,contentLoadingDepth+(on?1:-1))" in SWIPE
    assert "messages.classList.toggle('session-switch-loading',visible)" in SWIPE
    assert "const reducedMotion=()=>media('(prefers-reduced-motion: reduce)')" in SWIPE


def test_mobile_navigation_remains_available_while_a_prior_tab_is_loading():
    assert "let switching=false" not in SWIPE
    assert "||switching" not in SWIPE
    assert "navigationSid=targetSid" in SWIPE
    assert "const generation=++navigationGeneration" in SWIPE
    assert "if(generation!==navigationGeneration) return" in SWIPE
    assert "const currentSid=()=>navigationSid||actualSid()" in SWIPE
    assert "if(token!==activeNavigationLoadingToken) return" in SWIPE


def test_mobile_tab_switch_reprioritizes_the_bounded_warm_cache():
    assert "_prioritizeMobileSessionWarmCache(visibleSessionIds(),targetSid)" in SWIPE
    assert "function _prioritizeMobileSessionWarmCache(visibleIds,selectedSid)" in SESSIONS
    assert "priority.length<_SESSION_MESSAGE_CACHE_MAX" in SESSIONS
    assert "_sessionMessagePrefetchQueue=_sessionMessagePrefetchTargets().map" in SESSIONS
    assert "_pumpSessionMessagePrefetchQueue();" in SESSIONS
    assert "const _SESSION_MESSAGE_PREFETCH_CONCURRENCY = 2" in SESSIONS


def test_mobile_tabs_are_a_coupled_pager_and_share_switch_loading():
    for element_id in (
        "mobileSessionTabsViewport",
        "mobileSessionTabsTrack",
        "mobileSessionTabList",
        "btnTitlebarNewChat",
    ):
        assert f'id="{element_id}"' in INDEX
    assert "const sessions=tabSessions()" in SWIPE
    assert "if(!sid) return []" in SWIPE
    assert "temporary:true" not in SWIPE
    assert "data-temporary" not in SWIPE
    assert "tabList.replaceChildren(...sessions.map(session=>buildTab(session,activeSid)))" in SWIPE
    assert "tabList.addEventListener('click',onTabClick)" in SWIPE
    assert "centerActiveTab" in SWIPE
    assert "switchTarget(target,'mobile-session-swipe')" in SWIPE
    assert ".mobile-session-tabs{display:none;}" in CSS
    assert ".mobile-session-tabs{display:block;" in CSS
    assert ".mobile-session-tabs-viewport{position:relative;width:100%;" in CSS
    viewport_rule = CSS[CSS.index(".mobile-session-tabs-viewport{"):]
    viewport_rule = viewport_rule[: viewport_rule.index("}") + 1]
    assert "overflow:hidden" in viewport_rule
    assert "touch-action:pan-y" in viewport_rule
    assert "scroll-snap-type" not in viewport_rule
    assert '.mobile-session-tab[aria-selected="true"]' in CSS
    assert ".app-titlebar-new-chat.mobile-session-new-tab{" in CSS


def test_mobile_tab_boundaries_plus_position_and_session_state_are_explicit():
    track_start = INDEX.index('id="mobileSessionTabsTrack"')
    list_position = INDEX.index('id="mobileSessionTabList"', track_start)
    plus_position = INDEX.index('id="btnTitlebarNewChat"', track_start)
    track_end = INDEX.index('</div>', plus_position)
    assert list_position < plus_position < track_end
    assert "mobileSessionTabPrevious" not in INDEX
    assert "mobileSessionTabNext" not in INDEX
    assert ".mobile-session-tabs-track::before" in CSS
    assert ".mobile-session-tabs-track::after" in CSS
    assert ".mobile-session-tab.is-loading::before" not in CSS
    assert "mobile-session-tab-spin" not in CSS
    assert "tabsRoot.setAttribute('aria-busy'" not in SWIPE
    assert "mobile-session-tab-state session-state-indicator" in SWIPE
    assert "row.classList.contains('streaming')" in SWIPE
    assert "row.classList.contains('unread')" in SWIPE
    assert "row.classList.contains('needs-attention')" in SWIPE


def test_selected_tab_uses_sidebar_style_gray_without_accent_line():
    selected = CSS[CSS.index('.mobile-session-tab[aria-selected="true"]'):]
    selected = selected[: selected.index("}") + 1]
    assert "var(--surface-subtle-hover,var(--hover-bg))" in selected
    assert "border-color:var(--border)" in selected
    assert "box-shadow:none" in selected
    assert '.mobile-session-tab[aria-selected="true"]::after' not in CSS


def test_session_switch_loading_matches_classic_or_high_signal_layout():
    assert 'id="sessionSwitchSkeleton"' in INDEX
    assert 'class="session-switch-skeleton-classic"' in INDEX
    assert INDEX.count('class="session-switch-skeleton-chat-row') == 4
    assert 'class="session-switch-skeleton-high-signal"' in INDEX
    assert INDEX.count('class="session-switch-skeleton-pane"') == 4
    for label in ("Goal", "Status", "Last instruction", "Result"):
        assert f'<span class="session-switch-skeleton-pane-label">{label}</span>' in INDEX
    assert 'html[data-session-view="classic"] .session-switch-skeleton-high-signal' in CSS
    assert 'html[data-session-view="dashboard"] .session-switch-skeleton-classic' in CSS
    assert ".session-switch-skeleton-high-signal{height:100%;min-height:0;display:grid;grid-template-rows:repeat(4,minmax(0,1fr))" in CSS
    assert ".messages.session-switch-loading > .session-dashboard" in CSS
    assert "animation:skeletonSheen 1.25s ease-in-out infinite" in CSS
    reduced_motion_rule = (
        "@media (prefers-reduced-motion:reduce){\n"
        "    .session-switch-skeleton-avatar,.session-switch-skeleton-role-line,.session-switch-skeleton-line{animation:none;}"
    )
    assert reduced_motion_rule in CSS
    assert CSS.index(reduced_motion_rule) > CSS.index(".session-switch-skeleton-avatar,.session-switch-skeleton-role-line,.session-switch-skeleton-line{background:")
    assert "messages.setAttribute('aria-busy',visible?'true':'false')" in SWIPE
    assert "function ensureContentSkeleton()" in SWIPE
    assert "const skeleton=ensureContentSkeleton()" in SWIPE
    assert "if(skeleton) skeleton.hidden=!visible" in SWIPE


def test_partial_swipe_reveals_an_adjacent_view_specific_loading_surface():
    assert "function applySwipeVisual(dx,target,direction)" in SWIPE
    assert "const base=direction<0?width:-width" in SWIPE
    assert "contentSurface.style.transform=`translate3d(${dx}px,0,0)`" in SWIPE
    assert "preview.style.transform=`translate3d(${base+dx}px,0,0)`" in SWIPE
    assert "surface.classList.add('session-swipe-active')" in SWIPE
    assert "await animateSwipeTo(active.direction<0?-width:width,0,targetTabLeft)" in SWIPE
    assert ".messages-shell.session-swipe-active{overflow:hidden;}" in CSS
    assert ".messages.session-swipe-moving" in CSS
    assert ".session-swipe-preview.session-swipe-moving" in CSS
    assert "pointer-events:none" in CSS[CSS.index(".session-swipe-preview{"):CSS.index("}", CSS.index(".session-swipe-preview{"))]


def test_tab_header_and_chat_use_the_same_swipe_progress():
    assert "tabsViewport.addEventListener('pointerdown',start,{passive:true})" in SWIPE
    assert "surface.addEventListener('pointerdown',start,{passive:true})" in SWIPE
    assert "const fromTabs=!!(tabsViewport&&event.target&&tabsViewport.contains(event.target))" in SWIPE
    assert "if(fromTabs&&event.target.closest&&event.target.closest('.mobile-session-new-tab')) return" in SWIPE
    assert "const progress=Math.min(1,Math.abs(dx)/swipeWidth())" in SWIPE
    assert "setTabScroll(gesture.tabStartScrollLeft+(targetLeft-gesture.tabStartScrollLeft)*progress)" in SWIPE
    assert "applyTabSwipeProgress(dx,target)" in SWIPE
    assert "active.tabStartScrollLeft" in SWIPE
    assert "suppressTabClickUntil=performance.now()+450" in SWIPE


def test_desktop_sidebar_and_keyboard_session_switches_use_the_same_skeleton():
    assert "setContentLoading," in SWIPE
    assert "const setSessionContentLoading=window.__sessionSwipeNavigation&&window.__sessionSwipeNavigation.setContentLoading" in SESSIONS
    assert "if(manageSessionContentLoading&&typeof setSessionContentLoading==='function') setSessionContentLoading(true)" in SESSIONS
    assert "if(manageSessionContentLoading&&typeof setSessionContentLoading==='function') setSessionContentLoading(false)" in SESSIONS
    assert "_openSidebarSession(session,{source:'keyboard-session-navigation'})" in SESSIONS


def test_mobile_session_selection_recenters_after_revealing_the_tab_strip():
    open_start = SESSIONS.index("async function _openSidebarSession")
    close_position = SESSIONS.index("closeMobileSidebar(true)", open_start)
    load_position = SESSIONS.index("await loadSession", open_start)
    sync_position = SESSIONS.index("syncSessionTabs(true)", open_start)
    render_position = SESSIONS.index("renderSessionListFromCache()", open_start)
    assert "const wasMobileSessionPage=document.documentElement.dataset.mobileSessionView==='sessions';" in SESSIONS
    assert "if(wasMobileSessionPage&&typeof closeMobileSidebar==='function') closeMobileSidebar(true);" in SESSIONS
    assert "if(wasMobileSessionPage&&typeof syncSessionTabs==='function') syncSessionTabs(true);" in SESSIONS
    assert close_position < load_position < sync_position < render_position
    assert "if(wasMobileSessionPage&&!openedTarget&&typeof openMobileSessionPage==='function') openMobileSessionPage();" in SESSIONS
