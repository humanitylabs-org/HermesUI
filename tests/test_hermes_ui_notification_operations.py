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
    assert "tailnet-scheduled-job-more" not in RAIL
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


def test_scheduled_jobs_are_grouped_chronologically_without_repeated_status_tags():
    assert "const SCHEDULED_JOB_GROUPS=[" in RAIL
    for key in ("running", "failed", "active", "paused", "disabled", "readonly"):
        assert f"key:'{key}'" in RAIL
    assert "scheduledJobSort(job,groupKey)" in RAIL
    assert "groupKey==='active'||groupKey==='paused'" in RAIL
    assert "scheduledJobTime(job,['next_run_at'])" in RAIL
    assert "direction:-1" in RAIL
    assert "jobs.sort((left,right)=>" in RAIL
    assert "group.className=`tailnet-scheduled-group is-${groupMeta.key}`" in RAIL
    assert "tailnet-scheduled-group-head" in RAIL
    assert "tailnet-scheduled-group-count" in RAIL
    assert "tailnet-scheduled-status" not in RAIL


def test_job_actions_open_from_the_whole_row_on_context_long_press_or_keyboard():
    assert "SCHEDULED_JOB_LONG_PRESS_MS=450" in RAIL
    assert "row.addEventListener('contextmenu'" in RAIL
    assert "row.addEventListener('pointerdown'" in RAIL
    assert "row.addEventListener('pointermove'" in RAIL
    assert "event.key==='ContextMenu'||(event.shiftKey&&event.key==='F10')" in RAIL
    assert "event.key==='Enter'||event.key===' '" in RAIL
    assert "Right-click or hold a job for actions" in RAIL
    assert "row.tabIndex=0" in RAIL
    assert "scheduledJobLongPress.row.classList.remove('is-pressing')" in RAIL


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


def test_contained_reply_composer_reuses_canonical_controls_without_touching_main_chat():
    for element_id in (
        "tailnetNotificationThreadAttach",
        "tailnetNotificationThreadFileInput",
        "tailnetNotificationThreadPrompts",
        "tailnetNotificationThreadModelChip",
        "tailnetNotificationThreadModelSelect",
        "tailnetNotificationThreadModelDropdown",
    ):
        assert f'id="{element_id}"' in INDEX
    assert 'class="tailnet-notification-thread-composer composer-box"' in INDEX
    assert 'class="tailnet-notification-thread-footer"' in INDEX
    assert 'class="composer-footer tailnet-notification-thread-footer"' not in INDEX
    assert 'class="send-btn has-tooltip has-tooltip--left tailnet-notification-thread-send"' in INDEX
    assert 'class="tailnet-notification-thread-action-slot"' in INDEX
    assert "does not change the main chat" in INDEX
    assert '<polyline points="5 12 12 5 19 12"/>' in INDEX
    assert "uploadPendingFiles({clearPending:false,sessionId:notificationThreadSession.session_id,files:filesSnapshot})" in RAIL
    assert "api('/api/prompts')" in RAIL
    assert "renderModelDropdown({" in RAIL
    assert "dropdownId:'tailnetNotificationThreadModelDropdown'" in RAIL
    assert "api('/api/session/update'" in RAIL
    assert "model:notificationThreadModel.model||notificationThreadSession.model||undefined" in RAIL
    assert "attachments:uploaded.length?uploaded:undefined" in RAIL


def test_contained_reply_sessions_are_removed_before_every_sidebar_render_path():
    assert "let _containedCronReplySessions = [];" in SESSIONS
    assert "function _isContainedCronReplySession(session)" in SESSIONS
    assert "_containedCronReplySessions=receivedSessions.filter(_isContainedCronReplySession);" in SESSIONS
    assert "const serverSessions=receivedSessions.filter(session=>!_isContainedCronReplySession(session));" in SESSIONS
    assert "sessData.sidebar_reference_sessions.filter(session=>!_isContainedCronReplySession(session))" in SESSIONS
    assert SESSIONS.index("const serverSessions=receivedSessions.filter") < SESSIONS.index("_allSessions = _mergeOptimisticFirstTurnSessions(serverSessions)")


def test_notifications_layout_is_compact_responsive_and_thread_composer_stays_below_messages():
    assert ".tailnet-notifications-mode-button.is-active" in STYLE
    assert ".tailnet-scheduled-group{" in STYLE
    assert ".tailnet-scheduled-job{" in STYLE
    assert ".tailnet-scheduled-job-menu{" in STYLE
    assert ".tailnet-cron-edit-dialog{" in STYLE
    assert ".tailnet-notification-thread-pinned{box-sizing:border-box;flex:0 0 auto;height:clamp(150px,30vh,260px);max-height:260px;overflow-y:auto" in STYLE
    assert ".tailnet-notification-thread-messages{display:flex;flex:1 1 auto" in STYLE
    assert "overflow-y:auto;overscroll-behavior:contain" in STYLE
    assert ".tailnet-notification-thread .tailnet-notification-thread-composer.composer-box{position:relative" in STYLE
    assert "@media(max-width:640px)" in STYLE
    assert ".tailnet-scheduled-job{display:block;min-height:54px" in STYLE
    assert ".tailnet-notification-thread-pinned{height:190px;max-height:190px;}" in STYLE
    assert ".tailnet-scheduled-job-more{" not in STYLE
    assert "right:60px" in STYLE


def test_dark_mode_send_controls_use_light_fill_and_dark_foreground():
    assert ":root.dark button.send-btn:not(.stop):not(.interrupt):not(.steer){background:#f8fafc!important" in STYLE
    assert "color:#111827!important" in STYLE
    assert "tailnet-notification-thread-send" in STYLE
    assert "background:rgba(255,255,255,.24)!important" in STYLE
