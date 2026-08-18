from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
SW = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
SWIPE = (ROOT / "static" / "session-swipe-navigation.js").read_text(encoding="utf-8")
SESSIONS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")


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
    assert "if(!enabled()||switching||gesture||!currentSid()) return" in SWIPE
    assert "@media (max-width:640px) and (pointer:coarse){.messages-shell{touch-action:pan-y;}}" in CSS


def test_swipe_uses_visible_sidebar_order_and_existing_session_switch_path():
    assert "_sessionVisibleSidebarIds" in SWIPE
    assert "const targetSid=ids[index+(direction<0?1:-1)]" in SWIPE
    assert "_allSessions.find" in SWIPE
    assert "_openSidebarSession(target,{source})" in SWIPE
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
    assert "transformPane" not in SWIPE
    assert "Release to open" not in SWIPE


def test_swipe_does_not_start_on_edges_or_interactive_content():
    assert "const EDGE_GUARD=22" in SWIPE
    assert "event.clientX<=EDGE_GUARD||event.clientX>=window.innerWidth-EDGE_GUARD" in SWIPE
    for selector in ("button", "a", "input", "textarea", "pre", "code", ".markdown-table-wrap"):
        assert selector in SWIPE
    assert "event.target.closest(INTERACTIVE_SELECTOR)" in SWIPE
    assert "selection.type==='Range'&&!selection.isCollapsed" in SWIPE


def test_swipe_and_tab_click_share_one_loading_experience():
    assert ".session-swipe-preview{" not in CSS
    assert "session-swipe-preview" not in SWIPE
    assert "void switchTarget(sessionForSid(sid),'mobile-session-tab')" in SWIPE
    assert "await switchTarget(target,'mobile-session-swipe')" in SWIPE
    assert "setContentLoading(true)" in SWIPE
    assert "setContentLoading(false)" in SWIPE
    assert "contentLoadingDepth=Math.max(0,contentLoadingDepth+(on?1:-1))" in SWIPE
    assert "messages.classList.toggle('session-switch-loading',visible)" in SWIPE
    assert "const reducedMotion=()=>media('(prefers-reduced-motion: reduce)')" in SWIPE


def test_mobile_browser_tabs_are_scrollable_and_share_switch_loading():
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
    assert "transformTabs" not in SWIPE
    assert "switchTarget(target,'mobile-session-swipe')" in SWIPE
    assert ".mobile-session-tabs{display:none;}" in CSS
    assert ".mobile-session-tabs{display:block;" in CSS
    assert ".mobile-session-tabs-viewport{position:relative;width:100%;" in CSS
    assert "overflow-x:auto" in CSS
    assert "scroll-snap-type:x proximity" in CSS
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


def test_session_switch_loading_is_content_skeleton_only():
    assert 'id="sessionSwitchSkeleton"' in INDEX
    assert INDEX.count('class="session-switch-skeleton-card"') == 3
    assert ".session-switch-skeleton:not([hidden]){display:grid;" in CSS
    assert ".messages.session-switch-loading > .session-dashboard" in CSS
    assert "animation:skeletonSheen 1.25s ease-in-out infinite" in CSS
    assert "messages.setAttribute('aria-busy',visible?'true':'false')" in SWIPE
    assert "function ensureContentSkeleton()" in SWIPE
    assert "const skeleton=ensureContentSkeleton()" in SWIPE
    assert "if(skeleton) skeleton.hidden=!visible" in SWIPE


def test_desktop_sidebar_and_keyboard_session_switches_use_the_same_skeleton():
    assert "setContentLoading," in SWIPE
    assert "const setSessionContentLoading=window.__sessionSwipeNavigation&&window.__sessionSwipeNavigation.setContentLoading" in SESSIONS
    assert "if(typeof setSessionContentLoading==='function') setSessionContentLoading(true)" in SESSIONS
    assert "if(typeof setSessionContentLoading==='function') setSessionContentLoading(false)" in SESSIONS
    assert "_openSidebarSession(session,{source:'keyboard-session-navigation'})" in SESSIONS
