from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
PANELS = (ROOT / "static" / "panels.js").read_text(encoding="utf-8")
BOOT = (ROOT / "static" / "boot.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_settings_popup_is_an_accessible_overlay_not_a_second_form():
    assert 'id="settingsPopup" hidden aria-hidden="true"' in INDEX
    assert 'id="settingsPopupSurface" role="dialog" aria-modal="true"' in INDEX
    assert 'aria-labelledby="settingsPopupTitle"' in INDEX
    assert 'id="settingsPopupClose"' in INDEX
    assert INDEX.count('id="mainSettings"') == 1
    assert INDEX.count('id="panelSettings"') == 1
    assert 'id="settingsPopupLayout"' in INDEX


def test_settings_open_moves_existing_menu_and_form_without_replacing_chat():
    assert "if (nextPanel === 'settings') {" in PANELS
    assert "openSettingsPopup();" in PANELS
    assert "layout.append(panel,main)" in PANELS
    assert "document.createComment('settings-panel-home')" in PANELS
    assert "document.createComment('settings-main-home')" in PANELS
    assert "mainEl.classList.toggle('showing-' + p, nextPanel === p)" in PANELS
    settings_branch = PANELS[PANELS.index("if (nextPanel === 'settings') {"):]
    settings_branch = settings_branch[: settings_branch.index("// ── Desktop sidebar collapse toggle")]
    assert "showing-settings" not in settings_branch
    assert "_currentPanel = nextPanel" not in settings_branch


def test_settings_popup_preserves_close_guards_focus_and_keyboard_access():
    assert "document.addEventListener('keydown',_onSettingsPopupKeydown,true)" in PANELS
    assert "document.removeEventListener('keydown',_onSettingsPopupKeydown,true)" in PANELS
    assert "if(event.key==='Escape')" in PANELS
    assert "if(event.key!=='Tab') return" in PANELS
    assert "_settingsPopupLastFocus=document.activeElement" in PANELS
    assert "focusTarget.focus()" in PANELS
    assert "close.focus({preventScroll:true})" in PANELS
    assert "setTimeout(()=>{if(close&&_settingsPopupOpen)close.focus({preventScroll:true});},0)" in PANELS
    assert "if (_settingsDirty)" in PANELS or "if(!_settingsDirty)" in PANELS
    assert "_showSettingsUnsavedBar()" in PANELS
    assert "typeof _isSettingsPopupOpen==='function'&&_isSettingsPopupOpen()" in BOOT


def test_popup_backdrop_and_mobile_sidebar_restore_are_explicit():
    assert 'data-settings-popup-backdrop' in INDEX
    assert "event.target.matches('[data-settings-popup-backdrop]')" in PANELS
    assert "closeMobileSidebar(true)" in PANELS
    assert "_settingsPopupSidebarWasOpen" in PANELS
    assert "openMobileSidebar(true)" in PANELS


def test_settings_popup_has_bounded_desktop_and_near_full_mobile_geometry():
    assert ".settings-popup{position:fixed;inset:0;z-index:1800" in CSS
    assert "body.settings-popup-open{overflow:hidden;}" in CSS
    assert "width:min(1080px,calc(100vw - 48px))" in CSS
    assert "height:min(780px,calc(100dvh - 48px))" in CSS
    assert ".settings-popup-layout{display:grid;grid-template-columns:240px minmax(0,1fr)" in CSS
    assert "@media(max-width:700px)" in CSS
    assert "width:calc(100vw - 16px);height:calc(100dvh - 16px)" in CSS
    assert "grid-template-rows:auto minmax(0,1fr)" in CSS
    assert ".settings-popup #settingsMenu .settings-menu-items{display:flex;flex-direction:row" in CSS
    assert ".settings-popup #mainSettings{display:flex!important" in CSS
