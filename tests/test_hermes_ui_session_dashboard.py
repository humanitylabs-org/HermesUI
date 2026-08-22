"""Focused contracts for HermesUI High Signal mode."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "static" / "session-dashboard.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
API_CONFIG = (ROOT / "api" / "config.py").read_text(encoding="utf-8")


def test_contextual_view_action_sits_beside_settings_and_never_reloads():
    footer = INDEX[INDEX.index('<div class="chat-settings-footer">'):INDEX.index('<div class="resize-handle"')]
    assert footer.index('id="chatSettingsToggle"') < footer.index('id="sessionViewToggle"')
    assert "Switch to High Signal mode" in footer
    assert "session-view-toggle-track" not in footer
    assert "Switch to Classic view" in DASHBOARD
    assert "Switch to High Signal mode" in DASHBOARD
    assert "window.history.replaceState" in DASHBOARD
    assert "location.reload" not in DASHBOARD


def test_high_signal_keeps_one_unboxed_goal_and_exactly_three_cards():
    start = INDEX.index('<section class="session-dashboard"')
    end = INDEX.index('<div class="messages-inner"', start)
    block = INDEX[start:end]
    assert block.count('<article class="session-dashboard-section session-dashboard-section--') == 4
    assert 'session-dashboard-section--original' in block
    assert 'session-dashboard-section--status' in block
    assert 'session-dashboard-section--instruction' in block
    assert 'session-dashboard-section--completed' in block
    assert 'id="sessionDashboardOriginalRequest"' in block
    assert 'id="sessionDashboardInstruction"' in block
    assert 'id="sessionDashboardStatus"' in block
    assert 'id="sessionDashboardCompleted"' in block
    assert 'id="sessionDashboardSummaryRefresh"' in block
    assert 'id="sessionDashboardRefresh"' in block
    assert block.index('>Goal<') < block.index('>Last instruction<') < block.index('>Status<') < block.index('>Result<')
    assert 'session-dashboard-heading-actions' in block
    assert block.index('>Goal<') < block.index('aria-label="Refresh goal"')
    assert block.index('>Status<') < block.index('aria-label="Refresh status"')
    assert 'data-session-view="dashboard"' in CSS
    assert 'data-session-view="classic"' in CSS


def test_goal_and_status_are_stateless_manual_only_model_summaries():
    assert "GROK_SUMMARY_ENDPOINT='/apps/api/high-signal-summary'" in DASHBOARD
    assert "method:'POST'" in DASHBOARD
    assert "credentials:'same-origin'" in DASHBOARD
    assert "Select Refresh to generate the goal summary." in DASHBOARD
    assert "Select Refresh to generate the current status." in DASHBOARD
    assert "AI • Manual refresh" in DASHBOARD
    assert "Refresh for latest" in DASHBOARD
    assert "maybeAutoRefreshSummaries" not in DASHBOARD
    assert "SUMMARY_AUTO_CHECK_MS" not in DASHBOARD
    assert "SUMMARY_AUTO_REFRESH_FLOOR_MS" not in DASHBOARD
    assert "setInterval(" not in DASHBOARD
    assert "visibilitychange" not in DASHBOARD
    assert "grokSummaryCache=new Map()" in DASHBOARD
    assert "localStorage.setItem('hermes-session-view'" in DASHBOARD
    assert "localStorage.setItem('grok" not in DASHBOARD.lower()
    assert "setMarkdown('sessionDashboardOriginalRequest',dashboardSessionSummary(projection))" not in DASHBOARD
    assert "renderGrokSummary('goal')" in DASHBOARD
    assert "renderGrokSummary('status')" in DASHBOARD


def test_goal_uses_bounded_opening_and_recent_evidence_without_full_history_fetch():
    assert "OPENING_EVIDENCE_LIMIT=30" in DASHBOARD
    assert "msg_before=${OPENING_EVIDENCE_LIMIT}&msg_limit=${OPENING_EVIDENCE_LIMIT}" in DASHBOARD
    assert ".filter(message=>message.role==='user')" in DASHBOARD
    assert "all.length>30?[...all.slice(0,8),...all.slice(-22)]:all" in DASHBOARD
    assert "lines:lines.slice(-80)" in DASHBOARD
    assert "openingEvidenceCache" in DASHBOARD


def test_high_signal_summary_has_a_normal_auxiliary_provider_slot():
    assert '{"key": "high_signal_summary", "label": "High Signal summaries"' in API_CONFIG
    assert '"description": "on-demand Goal and Status summaries"' in API_CONFIG


def test_refresh_calls_return_model_sentences_and_background_rows_feed_no_box():
    node = shutil.which("node")
    assert node is not None
    harness = f"""
const fs=require('fs');
const vm=require('vm');
const elements=new Map();
function element(id){{
  if(!elements.has(id)) elements.set(id,{{
    id,hidden:false,textContent:'',innerHTML:'',dataset:{{}},disabled:false,attrs:{{}},listeners:{{}},
    addEventListener(name,fn){{this.listeners[name]=fn;}},
    setAttribute(name,value){{this.attrs[name]=String(value);}},
    removeAttribute(name){{delete this.attrs[name];}},
  }});
  return elements.get(id);
}}
global.window=global;
global.document={{readyState:'complete',documentElement:{{dataset:{{sessionView:'dashboard'}}}},getElementById:element,addEventListener(){{}}}};
global.location={{href:'https://device.example/hermesUI/session/session-1'}};
global.history={{state:null,replaceState(){{}}}};
global.localStorage={{getItem(){{return null;}},setItem(){{}}}};
global.S={{session:{{session_id:'session-1'}},messages:[
  {{role:'user',content:'json:[{{"type":"text","text":"[Workspace::v1: /tmp]\\nBuild and ship the live dashboard.\\n\\n[Attached files: /tmp/screenshot.png]"}},{{"type":"image_url","image_url":{{"url":"data:image/png;base64,SECRET_PIXELS"}}}}]',id:'u1'}},
  {{role:'assistant',content:'I am deploying it now.',id:'a1',tool_calls:[{{function:{{name:'terminal'}}}}],finish_reason:'tool_calls'}},
  {{role:'user',content:'[ASYNC DELEGATION BATCH COMPLETE — review-1] Review finished.',_source:'process_wakeup',id:'b1'}},
  {{role:'assistant',content:'The dashboard is live and verified.',id:'a2',finish_reason:'stop'}},
  {{role:'user',content:'[IMPORTANT: Background process proc_1 completed (exit_code=0).]',_source:'process_wakeup',id:'b2'}},
  {{role:'assistant',content:'Independent review completed with no blockers.',id:'b3',finish_reason:'stop'}},
],busy:false,activeStreamId:null}};
global.msgContent=m=>String(m&&m.content||'');
global.renderMd=s=>String(s||'');
global._stripWorkspaceDisplayPrefix=s=>String(s||'').replace(/^\\s*\\[Workspace[^\\]]*\\]\\s*/i,'').trim();
global._stripAttachedFilesMarkerForDisplay=s=>String(s||'').replace(/\\s*\\[Attached files?:[\\s\\S]*?\\]\\s*$/i,'').trim();
global._messageIsRenderable=m=>!!(m&&m.role!=='tool'&&(m.content||(m.tool_calls||[]).length));
global._isContextCompactionMessage=()=>false;
global._isPreservedCompressionTaskListMessage=()=>false;
global._isRecoveryControlMessage=()=>false;
global.INFLIGHT={{}};
global.requestAnimationFrame=cb=>{{cb();return 1;}};
global.queueMicrotask=cb=>cb();
global._messagesTruncated=false;
global._oldestIdx=0;
const requests=[];
global.fetch=async(_url,opts)=>{{
  const body=JSON.parse(opts.body); requests.push(body);
  return {{ok:true,status:200,json:async()=>({{
    ok:true,kind:body.kind,summary:body.kind==='goal'?'The session goal is to ship the live dashboard.':'The dashboard has been shipped and the agent is waiting.',provider:'xai-oauth',model:'grok-4.20'
  }})}};
}};
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'session-dashboard.js'))},'utf8'));
(async()=>{{
  await new Promise(resolve=>setTimeout(resolve,25));
  const automaticRequests=requests.length;
  element('sessionDashboardSummaryRefresh').listeners.click();
  element('sessionDashboardRefresh').listeners.click();
  await new Promise(resolve=>setTimeout(resolve,25));
  syncSessionDashboard();
  process.stdout.write(JSON.stringify({{
    goal:element('sessionDashboardOriginalRequest').innerHTML,
    status:element('sessionDashboardStatus').innerHTML,
    instruction:element('sessionDashboardInstruction').innerHTML,
    result:element('sessionDashboardCompleted').innerHTML,
    automaticRequests,
    requests,
  }}));
}})().catch(error=>{{console.error(error);process.exit(1);}});
"""
    result = subprocess.run([node, "-e", harness], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload["goal"] == "The session goal is to ship the live dashboard."
    assert payload["status"] == "The dashboard has been shipped and the agent is waiting."
    assert payload["instruction"] == "Build and ship the live dashboard."
    assert payload["result"] == "The dashboard is live and verified."
    assert payload["automaticRequests"] == 0
    assert len(payload["requests"]) == 2
    assert {request["kind"] for request in payload["requests"]} == {"goal", "status"}
    combined = json.dumps(payload["requests"])
    assert "Independent review" not in combined
    assert "ASYNC DELEGATION" not in combined
    assert "Background process" not in combined
    assert "SECRET_PIXELS" not in combined
    assert "image_url" not in combined


def test_dashboard_projection_remains_incremental_for_long_sessions():
    node = shutil.which("node")
    assert node is not None
    harness = f"""
const fs=require('fs');const vm=require('vm');const elements=new Map();
function element(id){{if(!elements.has(id))elements.set(id,{{hidden:false,textContent:'',innerHTML:'',dataset:{{}},addEventListener(){{}},setAttribute(){{}},removeAttribute(){{}}}});return elements.get(id);}}
let reads=0;global.window=global;global.document={{readyState:'complete',documentElement:{{dataset:{{sessionView:'dashboard'}}}},getElementById:element,addEventListener(){{}}}};
global.location={{href:'https://device.example/hermesUI/'}};global.history={{state:null,replaceState(){{}}}};global.localStorage={{getItem(){{return null;}},setItem(){{}}}};
global.S={{session:{{session_id:'long'}},messages:Array.from({{length:10000}},(_,i)=>({{role:i%2?'assistant':'user',content:`message ${{i}}`,id:`m-${{i}}`}})),busy:false,activeStreamId:null}};
global.msgContent=m=>{{reads++;return String(m&&m.content||'');}};global.renderMd=s=>String(s||'');global._stripWorkspaceDisplayPrefix=s=>String(s||'');global._stripAttachedFilesMarkerForDisplay=s=>String(s||'');global._messageIsRenderable=()=>true;global._isContextCompactionMessage=()=>false;global._isPreservedCompressionTaskListMessage=()=>false;global._isRecoveryControlMessage=()=>false;global.INFLIGHT={{}};global.requestAnimationFrame=cb=>{{cb();return 1;}};global.queueMicrotask=cb=>cb();global._messagesTruncated=false;global._oldestIdx=0;
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'session-dashboard.js'))},'utf8'));
const initial=reads;for(let i=0;i<20;i++)syncSessionDashboard();const repeated=reads-initial;document.documentElement.dataset.sessionView='classic';const beforeClassic=reads;for(let i=0;i<20;i++)syncSessionDashboard();process.stdout.write(JSON.stringify({{initial,repeated,classic:reads-beforeClassic}}));
"""
    result = subprocess.run([node, "-e", harness], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload["initial"] >= 10000
    assert payload["repeated"] <= 500
    assert payload["classic"] == 0
