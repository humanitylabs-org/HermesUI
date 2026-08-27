from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
SW = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
SESSIONS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
BOOT = (ROOT / "static" / "boot.js").read_text(encoding="utf-8")
RAIL = (ROOT / "static" / "tailnet-app-rail.js").read_text(encoding="utf-8")
UI = (ROOT / "static" / "ui.js").read_text(encoding="utf-8")


def test_mobile_tabs_and_cross_session_swipe_are_retired_from_the_shell():
    for element_id in (
        "mobileSessionTabs",
        "mobileSessionTabsViewport",
        "mobileSessionTabsTrack",
        "mobileSessionTabList",
        "btnTitlebarNewChat",
    ):
        assert f'id="{element_id}"' not in INDEX
    assert "session-swipe-navigation.js" not in INDEX
    assert "session-swipe-navigation.js" not in SW
    assert "&labeled-adjacent-tabs=v1" not in INDEX
    assert "&labeled-adjacent-tabs=v1" not in SW
    assert ".mobile-session-tabs{display:block" not in CSS
    assert ".mobile-session-tab{" not in CSS
    assert ".messages-shell.session-swipe-active" not in CSS
    assert ".session-swipe-preview" not in CSS


def test_mobile_shell_reclaims_the_former_tab_titlebar_space():
    phone_start = CSS.index("@media(max-width:640px)")
    phone_css = CSS[phone_start:]
    assert ".app-titlebar{display:flex!important;height:34px" in phone_css
    assert 'html[data-mobile-session-view="sessions"] .app-titlebar,html[data-tailnet-view="external"] .app-titlebar{display:none!important;}' in phone_css
    assert ".app-titlebar-icon,.app-titlebar-sub,.app-titlebar-spacer,.app-titlebar-reload" in phone_css
    assert '<header class="app-titlebar" role="banner">' in INDEX
    assert ".app-titlebar{display:flex;align-items:center;justify-content:center;height:38px;" in CSS


def test_bottom_sessions_control_remains_the_mobile_navigation_path():
    assert 'id="mobilePrimaryMenu"' in INDEX
    assert 'id="mobileSessionsButton"' in INDEX
    assert "mobileSessionsButton.addEventListener('click'" in RAIL
    assert "window.openMobileSessionPage()" in RAIL
    assert "function openMobileSessionPage()" in BOOT
    assert "document.documentElement.dataset.mobileSessionView='sessions';" in BOOT
    assert "if(_mobileSessionSelectionRequired())return openMobileSessionPage();" in BOOT


def test_removed_assets_have_matching_cache_identities():
    identity = "&mobile-tabs-removed=v1"
    assert INDEX.count(identity) == 3
    assert SW.count(identity) == 3


def test_session_switch_loading_survives_without_the_swipe_module():
    assert 'id="sessionSwitchSkeleton"' in INDEX
    assert 'class="session-switch-skeleton-classic"' in INDEX
    assert INDEX.count('class="session-switch-skeleton-chat-row') == 4
    assert 'class="session-switch-skeleton-high-signal"' in INDEX
    assert INDEX.count('<article class="session-switch-skeleton-pane') == 4
    for label in ("Goal", "Status", "Last prompt", "Result"):
        assert f'<span class="session-switch-skeleton-pane-label">{label}</span>' in INDEX
    assert "let _sessionContentLoadingDepth=0" in SESSIONS
    assert "function _setSessionContentLoading(on)" in SESSIONS
    assert "messages.classList.toggle('session-switch-loading',visible)" in SESSIONS
    assert "messages.setAttribute('aria-busy',visible?'true':'false')" in SESSIONS
    assert "if(skeleton) skeleton.hidden=!visible" in SESSIONS
    assert "if(manageSessionContentLoading) _setSessionContentLoading(true)" in SESSIONS
    assert "if(manageSessionContentLoading) _setSessionContentLoading(false)" in SESSIONS
    assert "__sessionSwipeNavigation" not in SESSIONS
    assert ".messages.session-switch-loading > .session-dashboard" in CSS
    assert "animation:skeletonSheen 1.25s ease-in-out infinite" in CSS


def test_mobile_shell_has_no_swipe_down_refresh_gesture():
    assert "Pull-to-refresh for PWA standalone" not in UI
    assert "pull-to-refresh-indicator" not in UI
    assert "refreshSessionList('pull'" not in UI
    assert "pull-to-refresh-indicator" not in CSS
    assert "html,body{overscroll-behavior:none;}" in CSS


def test_destination_composer_is_immediate_and_draft_owned_during_loading():
    assert "const _composerNavigationDrafts = new Map()" in SESSIONS
    assert "function _beginComposerSessionNavigation(targetSid)" in SESSIONS
    assert "_composerDraftOwnerSid() !== sid" in SESSIONS
    assert "input.dataset.sessionDraftOwner = target" in SESSIONS
    assert "_composerNavigationOwnerSid === restoreSid" in SESSIONS
    assert "_finishComposerSessionNavigation(sid, true)" in SESSIONS
    assert "_finishComposerSessionNavigation(sid, false)" in SESSIONS
    assert "function _composerSessionNavigationPending()" in SESSIONS
    assert "This conversation is still loading" in UI


def test_mobile_session_selection_leaves_the_sessions_page_after_selection():
    open_start = SESSIONS.index("async function _openSidebarSession")
    close_before_load = SESSIONS.index("closeMobileSidebar(true)", open_start)
    load_position = SESSIONS.index("await loadSession", open_start)
    render_position = SESSIONS.index("renderSessionListFromCache()", open_start)
    assert "const wasMobileSessionPage=document.documentElement.dataset.mobileSessionView==='sessions';" in SESSIONS
    assert "if(wasMobileSessionPage&&typeof closeMobileSidebar==='function') closeMobileSidebar(true);" in SESSIONS
    assert close_before_load < load_position < render_position
    assert "if(wasMobileSessionPage&&!openedTarget&&typeof openMobileSessionPage==='function') openMobileSessionPage();" in SESSIONS
