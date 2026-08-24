from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
RAIL = (ROOT / "static" / "tailnet-app-rail.js").read_text(encoding="utf-8")
SESSIONS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
STYLE = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
PANELS = (ROOT / "static" / "panels.js").read_text(encoding="utf-8")


def test_notifications_default_and_scheduled_jobs_mode_contract():
    assert 'data-notifications-mode="notifications"' in INDEX
    assert 'data-notifications-mode="scheduled"' in INDEX
    assert "notificationsMode='notifications';" in RAIL
    assert "setNotificationFilter('unread');" in RAIL
    assert "api('/api/crons?all_profiles=1')" in RAIL
    assert "api('/api/crons/status')" in RAIL
    for action in ("run", "pause", "resume", "delete"):
        assert f"{action}:'/api/crons/{action}'" in RAIL
    assert "openScheduledJobEditor(job,trigger)" in RAIL
    assert "openCronEdit(job)" in RAIL
    assert "openCronCreate()" in RAIL
    assert "focusCancel:true" in RAIL


def test_scheduled_jobs_keep_actions_quiet_and_edit_in_a_reused_form_modal():
    for element_id in (
        "tailnetCronEditDialog",
        "tailnetCronEditMount",
        "tailnetCronEditCancel",
        "tailnetCronEditSave",
    ):
        assert f'id="{element_id}"' in INDEX
    assert "tailnet-scheduled-job-more" in RAIL
    assert "menu.hidden=true" in RAIL
    assert "detail.append(schedule)" not in RAIL
    assert "detail.append(mode)" not in RAIL
    assert "const body=document.getElementById('taskDetailBody');" in RAIL
    assert "cronEditMount.appendChild(body);" in RAIL
    assert "parent.insertBefore(body,nextSibling)" in RAIL
    assert "scrollTop:notificationsPanel?notificationsPanel.scrollTop:0" in RAIL
    assert "openScheduledJobEditor(job,trigger);" in RAIL
    assert "hermesui:cron-form-cancelled" in PANELS
    assert "hermesui:cron-form-saved" in PANELS


def test_notification_rows_preview_real_output_and_offer_reply():
    assert "notificationPreview(item.response)" in RAIL
    assert "reply.textContent='Reply'" in RAIL
    assert "hydrateNotificationRich(richBody,item)" in RAIL
    assert "Open to read" not in RAIL


def test_contained_reply_threads_use_persisted_sessions_and_normal_chat_streams():
    for element_id in (
        "tailnetNotificationThread",
        "tailnetNotificationThreadPinned",
        "tailnetNotificationThreadMessages",
        "tailnetNotificationThreadComposer",
        "tailnetNotificationThreadStop",
    ):
        assert f'id="{element_id}"' in INDEX
    assert "notificationReplyMarker(item)" in RAIL
    assert "Number(latest.message_count)<=12" in RAIL
    assert "const session=await findReplySession(item);" in RAIL
    assert "if(session)await loadReplySessionTranscript(session.session_id);" in RAIL
    assert "notificationsPanel.scrollTop=0" in RAIL
    assert "notificationThreadBack.focus({preventScroll:true})" in RAIL
    assert "api('/api/session/branch'" in RAIL
    assert "api('/api/session/new'" in RAIL
    assert "api('/api/session/rename'" in RAIL
    assert "api('/api/session/move'" in RAIL
    assert "project_id:null" in RAIL
    assert "api('/api/chat/start'" in RAIL
    assert "api(`/api/chat/cancel?stream_id=" in RAIL
    assert "new EventSource" in RAIL
    assert "Full run context" in RAIL
    assert "Notification output context" in RAIL
    assert "[End notification context]" in RAIL


def test_contained_reply_sessions_are_removed_before_every_sidebar_render_path():
    assert "let _containedCronReplySessions = [];" in SESSIONS
    assert "function _isContainedCronReplySession(session)" in SESSIONS
    assert "_containedCronReplySessions=receivedSessions.filter(_isContainedCronReplySession);" in SESSIONS
    assert "const serverSessions=receivedSessions.filter(session=>!_isContainedCronReplySession(session));" in SESSIONS
    assert "sessData.sidebar_reference_sessions.filter(session=>!_isContainedCronReplySession(session))" in SESSIONS
    assert SESSIONS.index("const serverSessions=receivedSessions.filter") < SESSIONS.index("_allSessions = _mergeOptimisticFirstTurnSessions(serverSessions)")


def test_notifications_layout_is_compact_responsive_and_thread_composer_is_sticky():
    assert ".tailnet-notifications-mode-button.is-active" in STYLE
    assert ".tailnet-scheduled-job{" in STYLE
    assert ".tailnet-scheduled-job-controls{" in STYLE
    assert ".tailnet-scheduled-job-menu{" in STYLE
    assert ".tailnet-cron-edit-dialog{" in STYLE
    assert ".tailnet-notification-thread-pinned{box-sizing:border-box;flex:0 0 auto;height:clamp(150px,30vh,260px);max-height:260px;overflow-y:auto" in STYLE
    assert ".tailnet-notification-thread-composer{position:sticky" in STYLE
    assert "@media(max-width:640px)" in STYLE
    assert ".tailnet-scheduled-job{grid-template-columns:minmax(0,1fr) 44px" in STYLE
    assert ".tailnet-notification-thread-pinned{height:190px;max-height:190px;}" in STYLE
    assert ".tailnet-scheduled-job-more{" in STYLE
    assert "right:60px" in STYLE


def test_dark_mode_send_controls_use_light_fill_and_dark_foreground():
    assert ":root.dark button.send-btn:not(.stop):not(.interrupt):not(.steer){background:#f8fafc!important" in STYLE
    assert "color:#111827!important" in STYLE
    assert ":root.dark .tailnet-notification-thread-send{background:#f8fafc;color:#111827" in STYLE
    assert "background:rgba(255,255,255,.24)!important" in STYLE
