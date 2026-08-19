import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "static" / "session-dashboard.js").read_text(encoding="utf-8")
COMMANDS = (ROOT / "static" / "commands.js").read_text(encoding="utf-8")


def test_high_signal_mode_is_frontend_only_and_keeps_classic_escape_hatch():
    assert "static/session-dashboard.js" in INDEX
    assert "hermes-session-view','classic'" in INDEX
    assert 'data-session-view="dashboard"' in CSS
    assert 'data-session-view="classic"' in CSS
    assert "fetch(" not in DASHBOARD
    assert "/api/" not in DASHBOARD


def test_fresh_install_defaults_to_classic_and_preserves_saved_high_signal_choice():
    assert "localStorage.getItem('hermes-session-view')" in INDEX
    assert "v=v==='dashboard'?'dashboard':'classic'" in INDEX
    assert "document.documentElement.dataset.sessionView='classic'" in INDEX
    assert "localStorage.setItem('hermes-session-view',v)" in INDEX
    assert "q==='high-signal'" in INDEX


def test_visible_mode_name_is_high_signal_not_dashboard():
    assert ">High Signal Mode</a>" in INDEX
    assert ">Dashboard view</a>" not in INDEX
    assert 'aria-label="High Signal Mode"' in INDEX
    assert 'href="?session_view=high-signal"' in INDEX


def test_high_signal_mode_has_exactly_four_full_space_sections():
    for element_id in (
        "sessionDashboardOriginalRequest",
        "sessionDashboardSummaryRefresh",
        "sessionDashboardSummaryUpdated",
        "sessionDashboardInstruction",
        "sessionDashboardStatus",
        "sessionDashboardTurn",
        "sessionDashboardCompleted",
        "sessionDashboardRefresh",
    ):
        assert f'id="{element_id}"' in INDEX
    assert '<div class="session-dashboard-label">Original request</div>' in INDEX
    assert '>Refresh summary</button>' in INDEX
    assert INDEX.count('<article class="session-dashboard-section') == 4
    assert 'session-dashboard-section--original' in INDEX
    assert 'session-dashboard-section--instruction' in INDEX
    assert 'session-dashboard-section--status' in INDEX
    assert 'session-dashboard-section--completed' in INDEX
    assert '<header class="session-dashboard-original">' not in INDEX
    assert '<article class="session-dashboard-card' not in INDEX
    assert "sessionDashboardSteersCard" not in INDEX
    assert INDEX.index('id="sessionDashboardInstruction"') < INDEX.index('id="sessionDashboardStatus"')
    assert INDEX.index('id="sessionDashboardStatus"') < INDEX.index('id="sessionDashboardCompleted"')
    assert ".session-dashboard{width:100%;max-width:none;height:100%" in CSS
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in CSS
    assert "grid-template-rows:repeat(2,minmax(0,1fr))" in CSS
    assert ".session-dashboard-section{min-width:0;min-height:0" in CSS
    assert "border-radius:0" in CSS
    assert "box-shadow:none" in CSS
    assert ".session-dashboard-section:nth-child(odd){border-right:1px solid var(--border);}" in CSS
    assert ".session-dashboard-section:nth-child(-n+2){border-bottom:1px solid var(--border);}" in CSS


def test_session_summary_uses_original_request_as_frontend_only_placeholder():
    assert "function dashboardSessionSummary(projection)" in DASHBOARD
    assert "typeof _messagesTruncated!=='undefined'" in DASHBOARD
    assert "typeof _oldestIdx!=='undefined'" in DASHBOARD
    assert "The original request is not loaded yet. Switch to Classic view and load earlier messages to see it." in DASHBOARD
    assert "const firstUser=projection.firstUser" in DASHBOARD
    assert "return firstText||'No original request is available yet.'" in DASHBOARD
    assert "setMarkdown('sessionDashboardOriginalRequest',dashboardSessionSummary(projection))" in DASHBOARD
    assert "function refreshDashboardSummary()" in DASHBOARD
    assert "summaryRefresh.addEventListener('click',refreshDashboardSummary)" in DASHBOARD
    assert "Placeholder refreshed" in DASHBOARD
    assert "compression_anchor_summary" not in DASHBOARD
    assert ".session-dashboard-section--original{" in CSS
    assert ".session-dashboard-copy--original{" in CSS


def test_truncated_tail_is_never_labeled_as_the_original_request():
    node = shutil.which("node")
    assert node is not None, "node is required for the dashboard provenance regression"
    harness = f"""
const fs=require('fs');
const vm=require('vm');
const elements=new Map();
function element(id){{
  if(!elements.has(id)) elements.set(id,{{id,hidden:false,textContent:'',innerHTML:'',dataset:{{}},addEventListener(){{}}}});
  return elements.get(id);
}}
global.window=global;
global.document={{
  readyState:'complete',
  documentElement:{{dataset:{{sessionView:'dashboard'}}}},
  getElementById:element,
  addEventListener(){{}}
}};
global.S={{session:{{session_id:'long',message_count:80}},messages:Array.from({{length:30}},(_,i)=>({{
  role:i%2?'assistant':'user',content:`TAIL user ${{i}}`,id:`m-${{i+50}}`
}})),busy:false,activeStreamId:null}};
global.msgContent=m=>String(m&&m.content||'');
global.renderMd=s=>String(s||'');
global._stripWorkspaceDisplayPrefix=s=>String(s||'');
global._stripAttachedFilesMarkerForDisplay=s=>String(s||'');
global._messageIsRenderable=()=>true;
global._isContextCompactionMessage=()=>false;
global._isPreservedCompressionTaskListMessage=()=>false;
global._isRecoveryControlMessage=()=>false;
global.INFLIGHT={{}};
global.requestAnimationFrame=cb=>{{cb();return 1;}};
global.queueMicrotask=cb=>cb();
let _messagesTruncated=true;
let _oldestIdx=50;
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'session-dashboard.js'))},'utf8'));
syncSessionDashboard();
process.stdout.write(JSON.stringify({{
  original:element('sessionDashboardOriginalRequest').innerHTML,
  tailWasMisrepresented:element('sessionDashboardOriginalRequest').innerHTML.includes('TAIL user'),
}}));
"""
    result = subprocess.run([node, "-e", harness], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload == {
        "original": "The original request is not loaded yet. Switch to Classic view and load earlier messages to see it.",
        "tailWasMisrepresented": False,
    }


def test_dashboard_reads_existing_session_state_without_mutating_messages():
    assert "current.messages" in DASHBOARD
    assert "INFLIGHT" in DASHBOARD
    assert "S.messages.push" not in DASHBOARD
    assert "S.messages=" not in DASHBOARD.replace(" ", "")
    assert "element.innerHTML=renderMd" in DASHBOARD
    assert "S.messages.push" not in DASHBOARD


def test_last_instruction_uses_the_latest_run_message_or_accepted_active_steer():
    assert "function latestRunUserEntries(entries)" in DASHBOARD
    assert "const accepted=acceptedSteersForActiveRun()" in DASHBOARD
    assert "accepted[accepted.length-1]" in DASHBOARD
    assert "runUsers[runUsers.length-1]" in DASHBOARD
    assert "sessionDashboardSteers" not in DASHBOARD
    assert "Steers added while working" not in INDEX
    assert "function acceptedSteersForActiveRun()" in DASHBOARD
    assert "window.recordSessionDashboardSteer=function(detail)" in DASHBOARD
    assert "window.recordSessionDashboardSteer({sessionId:ownerSid,streamId:ownerStreamId,text:steerDisplayText})" in COMMANDS
    assert "if(!state().busy&&!state().activeStreamId) return []" in DASHBOARD


def test_dashboard_updates_on_existing_render_and_busy_boundaries():
    assert "['renderMessages','setBusy','syncTopbar'].forEach(wrapAfter)" in DASHBOARD
    assert "scheduleSessionDashboardSync" in DASHBOARD
    assert "requestAnimationFrame" in DASHBOARD
    assert "window.syncSessionDashboard=syncSessionDashboard" in DASHBOARD
    assert "sessionDashboardRefresh" in DASHBOARD


def test_dashboard_projection_is_incremental_and_classic_view_skips_history_work():
    node = shutil.which("node")
    assert node is not None, "node is required for the dashboard performance regression"
    harness = f"""
const fs=require('fs');
const vm=require('vm');
const elements=new Map();
function element(id){{
  if(!elements.has(id)) elements.set(id,{{id,hidden:false,textContent:'',innerHTML:'',dataset:{{}},addEventListener(){{}}}});
  return elements.get(id);
}}
let reads=0;
global.window=global;
global.document={{
  readyState:'complete',
  documentElement:{{dataset:{{sessionView:'dashboard'}}}},
  getElementById:element,
  addEventListener(){{}}
}};
global.S={{session:{{session_id:'long'}},messages:Array.from({{length:10000}},(_,i)=>({{
  role:i%2?'assistant':'user',content:`message ${{i}}`,id:`m-${{i}}`
}})),busy:false,activeStreamId:null}};
global.msgContent=m=>{{reads++;return String(m&&m.content||'');}};
global.renderMd=s=>String(s||'');
global._stripWorkspaceDisplayPrefix=s=>String(s||'');
global._stripAttachedFilesMarkerForDisplay=s=>String(s||'');
global._messageIsRenderable=()=>true;
global._isContextCompactionMessage=()=>false;
global._isPreservedCompressionTaskListMessage=()=>false;
global._isRecoveryControlMessage=()=>false;
global.INFLIGHT={{}};
global.requestAnimationFrame=cb=>{{cb();return 1;}};
global.queueMicrotask=cb=>cb();
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'session-dashboard.js'))},'utf8'));
const afterInitial=reads;
for(let i=0;i<20;i++) syncSessionDashboard();
const repeated=reads-afterInitial;
S.messages=[...S.messages];
syncSessionDashboard();
const copied=reads-afterInitial-repeated;
S.messages.push({{role:'user',content:'new instruction',id:'m-10000'}});
syncSessionDashboard();
const appended=reads-afterInitial-repeated-copied;
document.documentElement.dataset.sessionView='classic';
const beforeClassic=reads;
for(let i=0;i<20;i++) syncSessionDashboard();
process.stdout.write(JSON.stringify({{
  initial:afterInitial,
  repeated,
  copied,
  appended,
  classic:reads-beforeClassic,
  hidden:element('sessionDashboard').hidden
}}));
"""
    result = subprocess.run([node, "-e", harness], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload["initial"] >= 10000
    assert payload["repeated"] <= 300
    assert payload["copied"] <= 15
    assert payload["appended"] <= 20
    assert payload["classic"] == 0
    assert payload["hidden"] is True


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
    assert "_isContextCompactionMessage" in DASHBOARD
    assert "_isPreservedCompressionTaskListMessage" in DASHBOARD
    assert "systemLikeText" not in DASHBOARD
    assert "body.charAt(0)==='['" not in DASHBOARD


def test_legitimate_bracket_prefixed_user_text_remains_dashboard_content():
    node = shutil.which("node")
    assert node is not None, "node is required for the dashboard behavior test"
    harness = f"""
const fs=require('fs');
const vm=require('vm');
const elements=new Map();
function element(id){{
  if(!elements.has(id)) elements.set(id,{{id,hidden:false,textContent:'',innerHTML:'',dataset:{{}},addEventListener(){{}}}});
  return elements.get(id);
}}
global.window=global;
global.document={{readyState:'complete',getElementById:element,addEventListener(){{}}}};
global.S={{session:{{session_id:'s1'}},messages:[
  {{role:'user',content:'[x] legitimate bracket-prefixed request'}},
  {{role:'assistant',content:'done'}},
],busy:false,activeStreamId:null}};
global.msgContent=m=>String(m&&m.content||'');
global.renderMd=s=>String(s||'');
global._stripWorkspaceDisplayPrefix=s=>String(s||'');
global._stripAttachedFilesMarkerForDisplay=s=>String(s||'');
global._messageIsRenderable=()=>true;
global._isContextCompactionMessage=()=>false;
global._isPreservedCompressionTaskListMessage=()=>false;
global._isRecoveryControlMessage=()=>false;
global.INFLIGHT={{}};
global.requestAnimationFrame=cb=>{{cb();return 1;}};
global.queueMicrotask=cb=>cb();
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'session-dashboard.js'))},'utf8'));
syncSessionDashboard();
process.stdout.write(JSON.stringify({{
  original:element('sessionDashboardOriginalRequest').innerHTML,
  instruction:element('sessionDashboardInstruction').innerHTML,
}}));
"""
    result = subprocess.run([node, "-e", harness], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload == {
        "original": "[x] legitimate bracket-prefixed request",
        "instruction": "[x] legitimate bracket-prefixed request",
    }


def test_dashboard_uses_existing_markdown_renderer():
    assert "typeof renderMd==='function'" in DASHBOARD
    assert ".session-dashboard-copy p" in CSS


def test_dashboard_long_markdown_is_contained_without_page_width_overflow():
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in CSS
    assert ".session-dashboard-section{min-width:0;min-height:0" in CSS
    assert ".session-dashboard-copy{min-width:0;max-width:100%" in CSS
    assert ".session-dashboard-copy pre{display:block;width:100%;min-width:0;max-width:100%;overflow-x:auto" in CSS
    assert ".session-dashboard-copy pre{background:var(--code-bg)" in CSS
    assert ".session-dashboard-copy pre code{background:none" in CSS
    assert ".session-dashboard-copy .pre-header+pre" in CSS
    assert ".session-dashboard-copy a,.session-dashboard-copy code:not(pre code)" in CSS
    assert ".session-dashboard-copy .markdown-table-wrap{overflow-x:auto;}" in CSS
    assert ".session-dashboard-copy--result{max-height:none;overflow:visible;}" in CSS


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
