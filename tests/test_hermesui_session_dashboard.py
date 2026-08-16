from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "static" / "session-dashboard.js").read_text(encoding="utf-8")
COMMANDS = (ROOT / "static" / "commands.js").read_text(encoding="utf-8")


def test_dashboard_is_frontend_only_and_keeps_classic_escape_hatch():
    assert "static/session-dashboard.js" in INDEX
    assert "hermes-session-view','classic'" in INDEX
    assert 'data-session-view="dashboard"' in CSS
    assert 'data-session-view="classic"' in CSS
    assert "fetch(" not in DASHBOARD
    assert "/api/" not in DASHBOARD


def test_dashboard_has_unboxed_original_request_and_conditional_steers_card():
    for element_id in (
        "sessionDashboardOriginalRequest",
        "sessionDashboardSummaryRefresh",
        "sessionDashboardSummaryUpdated",
        "sessionDashboardInstruction",
        "sessionDashboardSteersCard",
        "sessionDashboardSteers",
        "sessionDashboardStatus",
        "sessionDashboardTurn",
        "sessionDashboardCompleted",
        "sessionDashboardRefresh",
    ):
        assert f'id="{element_id}"' in INDEX
    assert '<div class="session-dashboard-label">Session summary</div>' in INDEX
    assert '>Refresh summary</button>' in INDEX
    assert 'class="session-dashboard-original"' in INDEX
    assert 'session-dashboard-card session-dashboard-card--goal' not in INDEX
    assert INDEX.count('<article class="session-dashboard-card') == 4
    assert INDEX.index('id="sessionDashboardInstruction"') < INDEX.index('id="sessionDashboardSteersCard"')
    assert INDEX.index('id="sessionDashboardSteersCard"') < INDEX.index('id="sessionDashboardStatus"')


def test_session_summary_uses_original_request_as_frontend_only_placeholder():
    assert "function dashboardSessionSummary(entries)" in DASHBOARD
    assert "entries.find(entry=>entry.message.role==='user'&&cleanUserText(entry.message))" in DASHBOARD
    assert "return firstText||'No original request is available yet.'" in DASHBOARD
    assert "setMarkdown('sessionDashboardOriginalRequest',dashboardSessionSummary(entries))" in DASHBOARD
    assert "function refreshDashboardSummary()" in DASHBOARD
    assert "summaryRefresh.addEventListener('click',refreshDashboardSummary)" in DASHBOARD
    assert "Placeholder refreshed" in DASHBOARD
    assert "compression_anchor_summary" not in DASHBOARD
    assert ".session-dashboard-original{" in CSS
    assert ".session-dashboard-copy--original{" in CSS


def test_dashboard_reads_existing_session_state_without_mutating_messages():
    assert "state().messages" in DASHBOARD
    assert "INFLIGHT" in DASHBOARD
    assert "S.messages.push" not in DASHBOARD
    assert "S.messages=" not in DASHBOARD.replace(" ", "")
    assert "element.innerHTML=renderMd" in DASHBOARD
    assert "S.messages.push" not in DASHBOARD


def test_mid_run_steers_use_a_separate_conditional_card_until_the_next_run():
    assert "function latestRunUserEntries(entries)" in DASHBOARD
    assert "function dashboardSteers(entries)" in DASHBOARD
    assert "runUsers.slice(1)" in DASHBOARD
    assert "map(line=>`> ${line}`)" in DASHBOARD
    assert "setMarkdown('sessionDashboardSteers',steers)" in DASHBOARD
    assert "steersCard.hidden=!steers" in DASHBOARD
    assert "Steers added while working" in INDEX
    assert ".session-dashboard-card--steers .session-dashboard-copy{color:var(--muted);}" in CSS
    assert ".session-dashboard-copy--verbatim blockquote{" in CSS
    assert "font-style:italic" in CSS
    assert "function acceptedSteersForActiveRun()" in DASHBOARD
    assert "window.recordSessionDashboardSteer=function(detail)" in DASHBOARD
    assert "window.recordSessionDashboardSteer({sessionId:ownerSid,streamId:ownerStreamId,text:steerDisplayText})" in COMMANDS
    assert "if(!state().busy&&!state().activeStreamId) return []" in DASHBOARD


def test_dashboard_updates_on_existing_render_and_busy_boundaries():
    assert "['renderMessages','setBusy','syncTopbar'].forEach(wrapAfter)" in DASHBOARD
    assert "window.syncSessionDashboard=syncSessionDashboard" in DASHBOARD
    assert "sessionDashboardRefresh" in DASHBOARD


def test_status_refresh_is_manual_only():
    assert "refresh.addEventListener('click',refreshDashboardStatus)" in DASHBOARD
    assert "setInterval(" not in DASHBOARD
    assert "Manual refresh only" in DASHBOARD
    assert "statusSnapshots" in DASHBOARD


def test_active_status_shows_assistant_messages_since_latest_instruction():
    assert "function assistantUpdatesSinceLatestInstruction(entries)" in DASHBOARD
    assert "entry.index>user.index" in DASHBOARD
    assert "entry.message.role==='assistant'" in DASHBOARD
    assert ".join('\\n\\n')" in DASHBOARD
    assert "if(updates) return updates" in DASHBOARD
    assert "setMarkdown('sessionDashboardStatus'" in DASHBOARD
    assert "The latest run has finished. Its completed result is available below." in DASHBOARD


def test_dashboard_filters_internal_system_messages():
    assert "message._source==='process_wakeup'" in DASHBOARD
    assert "systemLikeText" in DASHBOARD
    assert "_isContextCompactionMessage" in DASHBOARD
    assert "_isPreservedCompressionTaskListMessage" in DASHBOARD


def test_dashboard_uses_existing_markdown_renderer():
    assert "typeof renderMd==='function'" in DASHBOARD
    assert ".session-dashboard-copy p" in CSS


def test_dashboard_long_markdown_is_contained_without_page_width_overflow():
    assert "grid-template-columns:minmax(0,1fr)" in CSS
    assert ".session-dashboard-card{min-width:0;max-width:100%" in CSS
    assert ".session-dashboard-copy{min-width:0;max-width:100%" in CSS
    assert ".session-dashboard-copy pre{display:block;width:100%;min-width:0;max-width:100%;overflow-x:auto" in CSS
    assert ".session-dashboard-copy pre{background:var(--code-bg)" in CSS
    assert ".session-dashboard-copy pre code{background:none" in CSS
    assert ".session-dashboard-copy .pre-header+pre" in CSS
    assert ".session-dashboard-copy a,.session-dashboard-copy code:not(pre code)" in CSS
    assert ".session-dashboard-copy .markdown-table-wrap{overflow-x:auto;}" in CSS
    assert ".session-dashboard-copy--result{max-height:42vh;overflow-x:clip;overflow-y:auto;}" in CSS


def test_turn_badge_uses_only_explicit_existing_runtime_values():
    assert "function dashboardTurnProgress()" in DASHBOARD
    assert "current_turn" in DASHBOARD
    assert "max_turns" in DASHBOARD
    assert "Turn ${snapshot.turnProgress.turn} of ${snapshot.turnProgress.max}" in DASHBOARD
    assert "messages.filter" not in DASHBOARD
    assert ".session-dashboard-turn[hidden]{display:none;}" in CSS


def test_dashboard_never_hides_the_composer():
    dashboard_css = CSS[CSS.index(".session-view-switcher"): CSS.index("@media (hover:hover)", CSS.index(".session-view-switcher"))]
    assert "#composerWrap" not in dashboard_css
    assert "#msgInner" in dashboard_css
