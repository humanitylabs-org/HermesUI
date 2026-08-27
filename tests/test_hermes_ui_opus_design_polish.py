"""Focused contracts for the Opus-recommended HermesUI presentation polish."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "static" / "session-dashboard.js").read_text(encoding="utf-8")
SESSIONS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
UI = (ROOT / "static" / "ui.js").read_text(encoding="utf-8")
SW = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    start = source.index(f"function {name}")
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated function: {name}")


def test_high_signal_has_manual_trust_cues_and_quiet_empty_copy():
    render = _function_body(DASHBOARD, "renderGrokSummary")
    assert "record.fingerprint!==currentEvidence.fingerprint" in render
    assert "target.dataset.summaryState=record&&record.text?(stale?'stale':'current'):(error?'error':'empty')" in render
    assert "`· ${relative}${stale?' · stale':''}`" in render
    assert "The session has advanced since this summary was refreshed." in render
    assert '.session-dashboard-copy[data-summary-state="empty"]{color:var(--muted);}' in CSS
    assert '.session-dashboard-copy[data-summary-state="error"]{color:var(--error);}' in CSS
    assert ".session-dashboard-model-chip .composer-model-icon{display:none;}" in CSS
    assert "maybeAutoRefreshSummaries" not in DASHBOARD


def test_sessions_put_project_identity_before_title_and_state_at_the_right():
    project = SESSIONS.index("dot.className='session-project-dot'")
    title = SESSIONS.index("titleRow.appendChild(title)", project)
    assert project < title
    assert "const hasAttentionState=isStreaming||Boolean(attention);" in SESSIONS
    assert "state.className='session-attention-indicator session-state-indicator'+(isStreaming?' is-streaming':'')+attentionDotClass" in SESSIONS
    assert "+(hasUnread?' is-unread':'')" not in SESSIONS[SESSIONS.index("const attentionDotClass="):SESSIONS.index("state.setAttribute('aria-hidden','true')", SESSIONS.index("const attentionDotClass="))]
    assert ".session-item.streaming,.session-item.needs-attention,.session-item:focus-within,.session-item.menu-open{padding-right:40px;}" in CSS


def test_mobile_adjacent_tabs_are_retired_in_favor_of_the_sessions_menu():
    assert "session-swipe-navigation.js" not in INDEX
    assert 'id="mobileSessionTabs"' not in INDEX
    assert 'id="mobilePrimaryMenu"' in INDEX
    assert ".app-titlebar{display:flex!important;height:34px" in CSS
    assert 'html[data-mobile-session-view="sessions"] .app-titlebar,html[data-tailnet-view="external"] .app-titlebar{display:none!important;}' in CSS


def test_conversation_settings_are_grouped_rule_lists_with_clear_verbs():
    pane = INDEX[INDEX.index('id="settingsPaneConversation"'):INDEX.index('id="settingsPaneAppearance"')]
    assert "hermes-action-grid" not in pane
    assert pane.count('class="hermes-action-list') == 3
    for label in ("Download", "Export", "Import", "Create link", "Revoke", "Clear"):
        assert f'<span class="settings-action-verb">{label}</span>' in pane
    assert pane.index('id="btnDownload"') < pane.index('id="btnExportJSON"') < pane.index('id="btnExportHTML"') < pane.index('id="btnImportJSON"')
    assert pane.index('id="btnImportJSON"') < pane.index('id="btnShareSession"') < pane.index('id="btnStopSharingSession"') < pane.index('id="btnClearConvModal"')
    assert ".hermes-action-groups{display:flex;flex-direction:column;margin-bottom:18px;}" in CSS
    assert ".hermes-action-list+.hermes-action-list{margin-top:12px;}" in CSS
    assert ".settings-action-btn>svg{display:none;}" in CSS
    assert ".settings-popup-surface:has(#settingsPaneConversation.active){height:auto;" in CSS
    assert ".settings-popup-close{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;flex:0 0 32px;padding:0;border:0;border-radius:0;" in CSS
    assert "box-shadow:inset 0 -2px var(--accent)" in CSS


def test_mode_control_is_separate_and_settled_duration_has_one_source():
    assert ".tailnet-session-view-toggle{position:relative;margin-bottom:7px;" in CSS
    assert ".tailnet-session-view-toggle::after" in CSS
    assert 'html[data-session-view="dashboard"] #sessionViewToggle{color:#fff;background:linear-gradient(145deg,#b06cff,#7437e8);' in CSS
    summary = _function_body(UI, "_syncToolCallGroupSummary")
    assert "? _activityProcessedElapsedLabel(group)" in summary
    assert ": t('processed_elapsed','');" in summary
    assert "_activitySettledProcessedLabel(group)" not in summary


def test_all_changed_shell_assets_have_matching_cache_identities():
    identities = (
        "&opus-polish=v1",
        "&classic-duration=v1",
        "&status-indicators=v1",
        "&summary-trust=v1",
        "&mobile-tabs-removed=v1",
        "&high-signal-toggle=v1",
        "&mobile-session-home=v1",
    )
    for identity in identities:
        assert identity in INDEX
        assert identity in SW
