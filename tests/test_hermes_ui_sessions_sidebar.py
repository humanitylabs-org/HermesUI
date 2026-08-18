from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
SESSIONS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_header_uses_session_language_and_compact_icon_actions():
    assert '<span>Sessions</span>' in INDEX
    for element_id in ("btnSessionSelectMode", "btnNewSessionFolder", "btnSessionSearch", "btnNewChat"):
        assert f'id="{element_id}"' in INDEX
    assert INDEX.index('id="btnSessionSelectMode"') < INDEX.index('id="btnNewSessionFolder"')
    assert INDEX.index('id="btnNewSessionFolder"') < INDEX.index('id="btnSessionSearch"')
    assert INDEX.index('id="btnSessionSearch"') < INDEX.index('id="btnNewChat"')
    assert 'aria-label="New session"' in INDEX
    assert 'placeholder="Filter sessions..."' in INDEX


def test_search_is_hidden_until_the_header_icon_opens_it():
    assert 'id="sessionSearchWrap" hidden' in INDEX
    assert 'onclick="toggleSessionSearchPanel()"' in INDEX
    assert "function toggleSessionSearchPanel()" in SESSIONS
    assert "wrap.hidden=false" in SESSIONS
    assert "wrap.hidden=true" in SESSIONS
    assert ".sidebar-search[hidden]{display:none;}" in CSS
    assert ".panel-head-btn.active,.panel-head-btn[aria-pressed=\"true\"]" in CSS


def test_project_filters_only_render_after_a_real_folder_exists():
    assert "if(_allProjects.length>0){" in SESSIONS
    assert "if(_allProjects.length>0||hasUnprojected){" not in SESSIONS
    assert "function createSessionProjectFromHeader()" in SESSIONS
    assert "message:'Folder name:'" in SESSIONS
    project_bar = SESSIONS[SESSIONS.index("// Project filter bar"):SESSIONS.index("// Profile filter toggle")]
    assert "project-create-btn" not in project_bar


def test_select_is_in_header_and_archive_is_at_list_bottom():
    assert 'onclick="toggleSessionSelectMode()"' in INDEX
    assert "selectModeButton.classList.toggle('active',_sessionSelectMode)" in SESSIONS
    assert "className='session-archive-toggle'" in SESSIONS
    archive_index = SESSIONS.index("className='session-archive-toggle'")
    group_render_index = SESSIONS.index("list.appendChild(wrapper);", SESSIONS.index("function renderSessionListFromCache()"))
    assert archive_index > group_render_index
    assert ".session-archive-toggle{" in CSS
