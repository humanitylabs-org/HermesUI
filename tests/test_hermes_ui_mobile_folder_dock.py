from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
SESSIONS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_session_folder_filters_have_a_dedicated_dock_before_the_scroll_list():
    dock = '<div class="session-project-dock" id="sessionProjectDock" role="group" aria-label="Folders" hidden></div>'
    assert dock in INDEX
    assert INDEX.index(dock) < INDEX.index('<div class="session-list" id="sessionList"></div>')
    assert "const projectDock=$('sessionProjectDock');" in SESSIONS
    assert "projectDock.replaceChildren();" in SESSIONS
    assert "(projectDock||list).appendChild(bar);" in SESSIONS
    assert "if(projectDock) projectDock.hidden=false;" in SESSIONS
    skeleton_start = SESSIONS.index("function showSessionListSkeleton(targetProfile)")
    skeleton_end = SESSIONS.index("function renderSessionListFromCache()")
    skeleton = SESSIONS[skeleton_start:skeleton_end]
    assert "projectDock.replaceChildren();" in skeleton
    assert "projectDock.hidden=true;" in skeleton


def test_mobile_folder_dock_is_after_the_scrolling_list_but_desktop_order_is_unchanged():
    assert ".session-project-dock[hidden]{display:none!important;}" in CSS
    mobile_start = CSS.index("/* Mobile chat polish:")
    mobile = CSS[mobile_start:CSS.index("@media(max-width:640px) and (hover:hover)", mobile_start)]
    assert ".sidebar.mobile-session-page .session-project-dock{" in mobile
    assert "order:1" in mobile
    assert "flex-wrap:wrap" in mobile
    assert "max-height:120px" in mobile
    assert "max-height:162px" in CSS
    assert "overflow-y:auto" in mobile
    assert "overflow-x:auto" not in mobile
    assert "margin:8px 10px 0" in mobile
    assert "border-radius:20px" in mobile
    assert "border:1px solid var(--glass-edge)" in mobile
    assert "backdrop-filter" not in mobile[mobile.index(".sidebar.mobile-session-page .session-project-dock{"):mobile.index(".sidebar.mobile-session-page .project-bar{")]
    assert ".sidebar.mobile-session-page .session-list{order:0" in mobile
    desktop = CSS[:mobile_start]
    assert ".session-project-dock{order:" not in desktop


def test_folder_dock_assets_share_one_cache_identity():
    token = "&mobile-folder-dock=v2"
    index_style = next(line for line in INDEX.splitlines() if "static/style.css?v=" in line)
    index_sessions = next(line for line in INDEX.splitlines() if "static/sessions.js?v=" in line)
    sw = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
    sw_style = next(line for line in sw.splitlines() if "'./static/style.css' + VQ" in line)
    sw_sessions = next(line for line in sw.splitlines() if "'./static/sessions.js' + VQ" in line)
    assert token in index_style and token in sw_style
    assert token in index_sessions and token in sw_sessions


def test_new_folder_action_moves_between_header_and_terminal_folder_chip():
    assert ".panel-head-btn[hidden]{display:none!important;}" in CSS
    assert "function _syncSessionFolderCreateAffordances(hasVisibleProjects)" in SESSIONS
    assert "headerFolderBtn.hidden=Boolean(hasVisibleProjects);" in SESSIONS
    assert "_syncSessionFolderCreateAffordances(false);" in SESSIONS
    assert "_syncSessionFolderCreateAffordances(visibleProjects.length>0);" in SESSIONS
    project_bar = SESSIONS[SESSIONS.index("// Project filter bar"):SESSIONS.index("// Profile filter toggle")]
    assert "addChip.type='button';" in project_bar
    assert "addChip.className='project-chip project-chip-new';" in project_bar
    assert "addChip.setAttribute('aria-label','New folder');" in project_bar
    assert "createSessionProjectFromHeader();" in project_bar
    assert "bar.appendChild(addChip);" in project_bar
    assert project_bar.index("allChip") < project_bar.index("noneChip")
    assert project_bar.index("for(const p of visibleProjects)") < project_bar.index("bar.appendChild(addChip)")


def test_folder_plus_is_an_action_not_a_selectable_filter():
    assert ".project-chip-new{" in CSS
    assert ".project-chip-new svg{" in CSS
    assert "folder-plus" in SESSIONS
    assert "aria-hidden=\"true\"" in SESSIONS
    assert "width:36px" in CSS
    assert "min-width:36px" in CSS


def test_folder_context_menu_is_clamped_above_mobile_navigation():
    assert "const mobileNav=mobileFolderDock?$('mobilePrimaryMenu'):null;" in SESSIONS
    assert "mobileNav.getBoundingClientRect().top-viewportMargin" in SESSIONS
    assert "usableBottom-menuRect.height" in SESSIONS
    assert "window.innerWidth-menuRect.width-viewportMargin" in SESSIONS
