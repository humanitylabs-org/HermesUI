from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
SESSIONS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_header_keeps_secondary_actions_but_moves_new_session_into_the_list():
    assert '<span>Sessions</span>' in INDEX
    for element_id in ("btnSessionSelectMode", "btnNewSessionFolder", "btnSessionSearch"):
        assert f'id="{element_id}"' in INDEX
    assert INDEX.index('id="btnSessionSelectMode"') < INDEX.index('id="btnNewSessionFolder"')
    assert INDEX.index('id="btnNewSessionFolder"') < INDEX.index('id="btnSessionSearch"')
    actions_start = INDEX.index('<div class="panel-head-actions">', INDEX.index('<span>Sessions</span>'))
    actions_end = INDEX.index('</div>', actions_start)
    assert 'id="btnNewChat"' not in INDEX[actions_start:actions_end]
    assert 'class="session-new-session-proxy" id="btnNewChat"' in INDEX
    assert "button.id='btnSessionListNewChat'" in SESSIONS
    assert "label.textContent='New session'" in SESSIONS
    assert "if(proxy&&!proxy.disabled) proxy.click();" in SESSIONS
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
    assert "const visibleProjects=_visibleSessionProjects();" in SESSIONS
    assert "if(visibleProjects.length>0){" in SESSIONS
    assert "if(_allProjects.length>0||hasUnprojected){" not in SESSIONS
    assert "function createSessionProjectFromHeader()" in SESSIONS
    assert "message:'Folder name:'" in SESSIONS
    project_bar = SESSIONS[SESSIONS.index("// Project filter bar"):SESSIONS.index("// Profile filter toggle")]
    assert "project-create-btn" not in project_bar


def test_reserved_cron_project_and_background_sessions_stay_out_of_the_viewer():
    assert "const _HIDDEN_CRON_PROJECT_NAME = 'cron jobs';" in SESSIONS
    assert "function _isHiddenCronProject(project)" in SESSIONS
    assert "function _visibleSessionProjects(projects=_allProjects)" in SESSIONS
    assert "function _isHiddenCronViewerSession(session, projects=_allProjects)" in SESSIONS
    assert "_isCronSessionForUnread(session)||sid.startsWith('cron_')" in SESSIONS
    assert "if(_isHiddenCronViewerSession(s)) continue;" in SESSIONS
    assert "if(_isHiddenCronViewerSession(s)) return false;" in SESSIONS
    assert "for(const p of _visibleSessionProjects())" in SESSIONS
    assert "for(const p of visibleProjects)" in SESSIONS
    assert "if(next!==NO_PROJECT_FILTER&&(_allProjects||[]).some(project=>" in SESSIONS


def test_select_is_in_header_and_archive_sits_between_done_and_working():
    assert 'onclick="toggleSessionSelectMode()"' in INDEX
    assert "selectModeButton.classList.toggle('active',_sessionSelectMode)" in SESSIONS
    assert "className='session-archive-toggle'" in SESSIONS
    assert "const appendArchiveControls=()=>{" in SESSIONS
    assert "if(g.status==='working') appendArchiveControls();" in SESSIONS
    assert "if(g.status==='done') appendArchiveControls();" in SESSIONS
    assert "appendArchiveControls();\n  appendNewSessionLauncher();" in SESSIONS
    assert ".session-archive-toggle{" in CSS
