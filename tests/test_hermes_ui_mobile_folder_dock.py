from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
SESSIONS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_session_folder_filters_have_a_dedicated_dock_before_the_scroll_list():
    dock = '<div class="session-project-dock" id="sessionProjectDock" hidden></div>'
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
    assert "overflow-x:auto" in mobile
    assert ".sidebar.mobile-session-page .session-list{order:0" in mobile
    desktop = CSS[:mobile_start]
    assert ".session-project-dock{order:" not in desktop


def test_folder_dock_assets_share_one_cache_identity():
    token = "&mobile-folder-dock=v1"
    index_style = next(line for line in INDEX.splitlines() if "static/style.css?v=" in line)
    index_sessions = next(line for line in INDEX.splitlines() if "static/sessions.js?v=" in line)
    sw = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
    sw_style = next(line for line in sw.splitlines() if "'./static/style.css' + VQ" in line)
    sw_sessions = next(line for line in sw.splitlines() if "'./static/sessions.js' + VQ" in line)
    assert token in index_style and token in sw_style
    assert token in index_sessions and token in sw_sessions
