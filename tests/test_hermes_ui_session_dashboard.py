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
PANELS = (ROOT / "static" / "panels.js").read_text(encoding="utf-8")


def test_contextual_view_action_stays_in_the_app_rail_and_never_reloads():
    rail_start = INDEX.index('<nav class="rail tailnet-app-rail"')
    rail = INDEX[rail_start:INDEX.index('</nav>', rail_start)]
    assert INDEX.count('id="sessionViewToggle"') == 1
    assert 'id="sessionViewToggle"' in rail
    assert rail.index('id="sessionViewToggle"') < rail.index('id="tailnetThemeToggle"')
    assert rail.count('tailnet-session-view-icon--signal') == 1
    assert 'tailnet-session-view-icon--classic' not in rail
    assert "chat-settings-footer" not in INDEX
    assert ".session-view-toggle" not in CSS
    assert "Turn High Signal mode off" in DASHBOARD
    assert "Turn High Signal mode on" in DASHBOARD
    assert "toggle.setAttribute('data-tooltip',label)" in DASHBOARD
    assert "toggle.setAttribute('aria-pressed',dashboard?'true':'false')" in DASHBOARD
    assert "window.history.replaceState" in DASHBOARD
    assert "location.reload" not in DASHBOARD


def test_high_signal_toggle_uses_one_signal_glyph_and_a_purple_power_glow():
    assert '.tailnet-session-view-icon{width:20px;height:20px;display:flex;' in CSS
    assert 'html[data-session-view="dashboard"] #sessionViewToggle{color:#fff;background:linear-gradient(145deg,#b06cff,#7437e8);' in CSS
    assert '@keyframes highSignalPowerGlow' in CSS
    assert 'filter:drop-shadow(0 0 4px rgba(255,255,255,.92))' in CSS
    assert '@media (prefers-reduced-motion:no-preference)' in CSS


def test_high_signal_uses_the_available_inline_width_without_resizing_sessions():
    assert '.sidebar{width:300px;' in CSS
    assert 'data-session-view="dashboard"] .layout > .sidebar{width:' not in CSS
    assert 'data-session-view="classic"] .layout > .sidebar{width:' not in CSS
    dashboard_rule = CSS[CSS.index(".session-dashboard{"):CSS.index("}", CSS.index(".session-dashboard{"))]
    section_rule = CSS[CSS.index(".session-dashboard-section{"):CSS.index("}", CSS.index(".session-dashboard-section{"))]
    assert "width:100%" in dashboard_rule and "max-width:none" in dashboard_rule
    assert "min-width:0" in section_rule and "max-width:100%" in section_rule


def test_goal_section_does_not_waste_vertical_space_with_extra_top_inset():
    assert ".session-dashboard-section:first-child" not in CSS
    assert ".session-switch-skeleton-pane:first-child" not in CSS
    assert CSS.count("grid-template-rows:auto auto auto minmax(0,1fr)") == 4
    assert ".session-dashboard-section--original{overflow:hidden;max-height:min(190px,24vh);}" in CSS
    assert ".session-dashboard-section--instruction{max-height:min(220px,28vh);}" in CSS
    assert ".session-dashboard-section--status{max-height:min(170px,22vh);}" in CSS


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
    assert 'id="sessionDashboardLoadEarlier" hidden' in block
    assert '>Earlier turns</button>' in block
    assert 'id="sessionDashboardStatus"' in block
    assert 'id="sessionDashboardCompleted"' in block
    assert 'id="sessionDashboardSummaryRefresh"' in block
    assert 'id="sessionDashboardRefresh"' in block
    assert block.index('>Goal<') < block.index('>Last prompt<') < block.index('>Status<') < block.index('>Result<')
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
    assert "AI • Manual refresh" not in DASHBOARD
    assert "Refresh for latest" not in DASHBOARD
    assert "summaryRelativeTime" in DASHBOARD
    assert "updatedAt:Date.now()" in DASHBOARD
    assert "maybeAutoRefreshSummaries" not in DASHBOARD
    assert "SUMMARY_AUTO_CHECK_MS" not in DASHBOARD
    assert "SUMMARY_AUTO_REFRESH_FLOOR_MS" not in DASHBOARD
    assert "setInterval(" not in DASHBOARD
    assert "visibilitychange" not in DASHBOARD
    assert "grokSummaryCache=new Map()" in DASHBOARD
    assert "localStorage.setItem('hermes-session-view'" in DASHBOARD


def test_goal_and_status_share_one_visible_global_model_selector():
    block = INDEX[INDEX.index('<section class="session-dashboard"'):INDEX.index('</section>', INDEX.index('<section class="session-dashboard"')) + len('</section>')]
    assert block.count('data-high-signal-model data-summary-kind=') == 2
    assert block.count('aria-controls="sessionDashboardModelDropdown"') == 2
    assert block.index('data-high-signal-model data-summary-kind="goal"') < block.index('aria-label="Refresh goal"')
    assert block.index('data-high-signal-model data-summary-kind="status"') < block.index('aria-label="Refresh status"')
    assert block.index('>Goal<') < block.index('id="sessionDashboardSummaryUpdated"') < block.index('data-summary-kind="goal"') < block.index('aria-label="Refresh goal"')
    assert block.index('>Status<') < block.index('id="sessionDashboardUpdated"') < block.index('data-summary-kind="status"') < block.index('aria-label="Refresh status"')
    assert 'id="sessionDashboardSummaryUpdated" hidden' in block
    assert 'id="sessionDashboardUpdated" hidden' in block
    assert "SUMMARY_MODEL_TASK='high_signal_summary'" in DASHBOARD
    assert "api('/api/model/auxiliary')" in DASHBOARD
    assert "api('/api/models')" in DASHBOARD
    assert "await api('/api/model/set'" in DASHBOARD
    assert "scope:'auxiliary',task:SUMMARY_MODEL_TASK,provider,model" in DASHBOARD
    assert "document.querySelectorAll('[data-high-signal-model]')" in DASHBOARD
    assert "if(summaryModelLoaded&&!force) return summaryModelConfig" in DASHBOARD
    assert "summaryModelLoaded=true" in DASHBOARD
    assert "grokSummaryCache.clear()" in DASHBOARD
    assert "hermesui:high-signal-model-changed" in DASHBOARD
    assert "task.task==='high_signal_summary'" in PANELS
    assert ".session-dashboard-model-chip" in CSS
    assert "const visual=window.visualViewport" in DASHBOARD
    assert "railRect.right+margin" in DASHBOARD
    assert "const availableWidth=Math.max(0,rightEdge-leftEdge)" in DASHBOARD
    assert "const availableHeight=openAbove?availableAbove:availableBelow" in DASHBOARD
    assert "localStorage.setItem('grok" not in DASHBOARD.lower()
    assert "setMarkdown('sessionDashboardOriginalRequest',dashboardSessionSummary(projection))" not in DASHBOARD
    assert "renderGrokSummary('goal')" in DASHBOARD
    assert "renderGrokSummary('status')" in DASHBOARD


def test_last_prompt_keeps_base_prompt_all_accepted_steers_and_copy_buttons():
    assert "const latestSteerRunBySession=new Map()" in DASHBOARD
    assert "renderDashboardInstruction(entries,resultAnchor)" in DASHBOARD
    assert 'class="session-dashboard-steer"' in DASHBOARD
    assert 'aria-label="Accepted steers"' in DASHBOARD
    assert "steers.push(text)" in DASHBOARD
    assert "latestSteerRunBySession.set(sid,{key,baseText})" in DASHBOARD
    assert "if(typeof highlightCode==='function') highlightCode(element)" in DASHBOARD
    assert "if(typeof addCopyButtons==='function') addCopyButtons(element)" in DASHBOARD
    assert ".session-dashboard-section--instruction{max-height:min(220px,28vh);}" in CSS


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


def test_refresh_calls_keep_background_rows_out_of_result_but_available_to_status():
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
  {{role:'assistant',content:'',id:'bg-tool',tool_calls:[{{function:{{name:'terminal'}}}}],finish_reason:'tool_calls'}},
  {{role:'tool',content:'BACKGROUND_QA_COMPLETE',id:'bg-tool-result'}},
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
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'message_projection.js'))},'utf8'));
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
    status_request = next(request for request in payload["requests"] if request["kind"] == "status")
    assert "Independent review" in json.dumps(status_request)
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
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'message_projection.js'))},'utf8'));
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'session-dashboard.js'))},'utf8'));
const initial=reads;for(let i=0;i<20;i++)syncSessionDashboard();const repeated=reads-initial;document.documentElement.dataset.sessionView='classic';const beforeClassic=reads;for(let i=0;i<20;i++)syncSessionDashboard();process.stdout.write(JSON.stringify({{initial,repeated,classic:reads-beforeClassic}}));
"""
    result = subprocess.run([node, "-e", harness], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload["initial"] >= 10000
    assert payload["repeated"] <= 500
    assert payload["classic"] == 0


def test_wakeup_that_resumes_tool_work_promotes_its_terminal_answer_to_result():
    node = shutil.which("node")
    assert node is not None
    harness = f"""
const fs=require('fs');const vm=require('vm');const elements=new Map();
function element(id){{if(!elements.has(id))elements.set(id,{{id,hidden:false,textContent:'',innerHTML:'',dataset:{{}},disabled:false,attrs:{{}},listeners:{{}},addEventListener(name,fn){{this.listeners[name]=fn;}},setAttribute(name,value){{this.attrs[name]=String(value);}},removeAttribute(name){{delete this.attrs[name];}}}});return elements.get(id);}}
global.window=global;global.document={{readyState:'complete',documentElement:{{dataset:{{sessionView:'dashboard'}}}},getElementById:element,addEventListener(){{}}}};
global.location={{href:'https://device.example/hermesUI/session/session-1'}};global.history={{state:null,replaceState(){{}}}};global.localStorage={{getItem(){{return null;}},setItem(){{}}}};
global.S={{session:{{session_id:'session-1'}},messages:[
  {{role:'user',content:'[Workspace::v1: /tmp]\\nAnalyze the CRM export.',id:'u1'}},
  {{role:'assistant',content:'',id:'start-work',tool_calls:[{{function:{{name:'terminal'}}}}],finish_reason:'tool_calls'}},
  {{role:'tool',content:'Background process proc_1 started.',id:'start-result'}},
  {{role:'assistant',content:'The export is running; I will verify it when it finishes.',id:'progress',finish_reason:'stop'}},
  {{role:'user',content:'[IMPORTANT: Background process proc_1 completed (exit_code=0).]',_source:'process_wakeup',id:'w1'}},
  {{role:'assistant',content:'',id:'work',tool_calls:[{{function:{{name:'terminal'}}}}],finish_reason:'tool_calls'}},
  {{role:'tool',content:'CRM_COUNTS_VERIFIED',id:'t1'}},
  {{role:'assistant',content:'The CRM export contains 3,486 verified contacts.',id:'final',finish_reason:'stop'}},
],busy:false,activeStreamId:null}};
global.msgContent=m=>String(m&&m.content||'');global.renderMd=s=>String(s||'');global._stripWorkspaceDisplayPrefix=s=>String(s||'').replace(/^\\s*\\[Workspace[^\\]]*\\]\\s*/i,'').trim();global._stripAttachedFilesMarkerForDisplay=s=>String(s||'');global._messageIsRenderable=m=>!!(m&&m.role!=='tool'&&(m.content||(m.tool_calls||[]).length));global._isContextCompactionMessage=()=>false;global._isPreservedCompressionTaskListMessage=()=>false;global._isRecoveryControlMessage=()=>false;global.INFLIGHT={{}};global.requestAnimationFrame=cb=>{{cb();return 1;}};global.queueMicrotask=cb=>cb();global._messagesTruncated=false;global._oldestIdx=0;global.fetch=async()=>{{throw new Error('manual summaries must not run');}};
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'message_projection.js'))},'utf8'));
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'session-dashboard.js'))},'utf8'));
setTimeout(()=>{{syncSessionDashboard();process.stdout.write(JSON.stringify({{prompt:element('sessionDashboardInstruction').innerHTML,result:element('sessionDashboardCompleted').innerHTML}}));}},20);
"""
    result = subprocess.run([node, "-e", harness], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload["prompt"] == "Analyze the CRM export."
    assert payload["result"] == "The CRM export contains 3,486 verified contacts."


def test_result_with_assistant_only_tail_automatically_pages_until_last_prompt():
    node = shutil.which("node")
    assert node is not None
    harness = f"""
const fs=require('fs');const vm=require('vm');const elements=new Map();
function element(id){{if(!elements.has(id))elements.set(id,{{id,hidden:false,textContent:'',innerHTML:'',dataset:{{}},disabled:false,attrs:{{}},listeners:{{}},addEventListener(name,fn){{this.listeners[name]=fn;}},setAttribute(name,value){{this.attrs[name]=String(value);}},removeAttribute(name){{delete this.attrs[name];}}}});return elements.get(id);}}
global.window=global;global.document={{readyState:'complete',documentElement:{{dataset:{{sessionView:'dashboard'}}}},getElementById:element,addEventListener(){{}}}};
global.location={{href:'https://device.example/hermesUI/session/session-1'}};global.history={{state:null,replaceState(){{}}}};global.localStorage={{getItem(){{return null;}},setItem(){{}}}};
global.S={{session:{{session_id:'session-1'}},messages:[{{role:'assistant',content:'The requested dashboard is now live.',id:'result-1',finish_reason:'stop'}}],busy:false,activeStreamId:null}};
global.msgContent=m=>String(m&&m.content||'');global.renderMd=s=>String(s||'');global._stripWorkspaceDisplayPrefix=s=>String(s||'').replace(/^\\s*\\[Workspace[^\\]]*\\]\\s*/i,'').trim();global._stripAttachedFilesMarkerForDisplay=s=>String(s||'');global._messageIsRenderable=m=>!!(m&&m.role!=='tool'&&m.content);global._isContextCompactionMessage=()=>false;global._isPreservedCompressionTaskListMessage=()=>false;global._isRecoveryControlMessage=()=>false;global.INFLIGHT={{}};global.requestAnimationFrame=cb=>{{cb();return 1;}};global.queueMicrotask=cb=>cb();global._messagesTruncated=true;global._oldestIdx=61;
const historyRequests=[];global.api=async url=>{{
  historyRequests.push(url);
  if(url.includes('msg_before=61')) return {{session:{{messages:[{{role:'assistant',content:'Earlier assistant continuation.',id:'a-older'}}],_messages_truncated:true,_messages_offset:31}}}};
  if(url.includes('msg_before=31')) return {{session:{{messages:[{{role:'user',content:'[Workspace::v1: /tmp]\\nMake the High Signal dashboard reliable.',id:'u-prompt'}}],_messages_truncated:false,_messages_offset:0}}}};
  throw new Error(`Unexpected URL: ${{url}}`);
}};
let summaryRequests=0;global.fetch=async()=>{{summaryRequests++;throw new Error('Summary refresh must remain manual');}};
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'message_projection.js'))},'utf8'));
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'session-dashboard.js'))},'utf8'));
setTimeout(()=>{{syncSessionDashboard();process.stdout.write(JSON.stringify({{prompt:element('sessionDashboardInstruction').innerHTML,result:element('sessionDashboardCompleted').innerHTML,goal:element('sessionDashboardOriginalRequest').innerHTML,status:element('sessionDashboardStatus').innerHTML,historyRequests,summaryRequests}}));}},40);
"""
    result = subprocess.run([node, "-e", harness], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload["prompt"] == "Make the High Signal dashboard reliable."
    assert payload["result"] == "The requested dashboard is now live."
    assert payload["goal"] == "Select Refresh to generate the goal summary."
    assert payload["status"] == "Select Refresh to generate the current status."
    assert payload["summaryRequests"] == 0
    assert len(payload["historyRequests"]) == 2
    assert "msg_before=61&msg_limit=30" in payload["historyRequests"][0]
    assert "msg_before=31&msg_limit=30" in payload["historyRequests"][1]


def test_empty_last_prompt_shows_existing_load_earlier_control_after_hydration():
    node = shutil.which("node")
    assert node is not None
    harness = f"""
const fs=require('fs');const vm=require('vm');const elements=new Map();
function element(id){{if(!elements.has(id))elements.set(id,{{id,hidden:id==='sessionDashboardLoadEarlier',textContent:'',innerHTML:'',dataset:{{}},disabled:false,attrs:{{}},listeners:{{}},addEventListener(name,fn){{this.listeners[name]=fn;}},setAttribute(name,value){{this.attrs[name]=String(value);}},removeAttribute(name){{delete this.attrs[name];}}}});return elements.get(id);}}
global.window=global;global.document={{readyState:'complete',documentElement:{{dataset:{{sessionView:'dashboard'}}}},getElementById:element,addEventListener(){{}}}};
global.location={{href:'https://device.example/hermesUI/session/session-1'}};global.history={{state:null,replaceState(){{}}}};global.localStorage={{getItem(){{return null;}},setItem(){{}}}};
global.S={{session:{{session_id:'session-1'}},messages:[{{role:'assistant',content:'A result whose prompt is outside the loaded tail.',id:'result-1',finish_reason:'stop'}}],busy:false,activeStreamId:null}};
global.msgContent=m=>String(m&&m.content||'');global.renderMd=s=>String(s||'');global._stripWorkspaceDisplayPrefix=s=>String(s||'').replace(/^\\s*\\[Workspace[^\\]]*\\]\\s*/i,'').trim();global._stripAttachedFilesMarkerForDisplay=s=>String(s||'');global._messageIsRenderable=m=>!!(m&&m.role!=='tool'&&m.content);global._isContextCompactionMessage=()=>false;global._isPreservedCompressionTaskListMessage=()=>false;global._isRecoveryControlMessage=()=>false;global.INFLIGHT={{}};global.requestAnimationFrame=cb=>{{cb();return 1;}};global.queueMicrotask=cb=>cb();global._messagesTruncated=true;global._oldestIdx=151;global._loadingOlder=false;
const historyRequests=[];global.api=async url=>{{historyRequests.push(url);const match=String(url).match(/msg_before=(\\d+)/);const before=match?Number(match[1]):0;return {{session:{{messages:[{{role:'assistant',content:'Still no user prompt.',id:'a-older-'+before}}],_messages_truncated:true,_messages_offset:Math.max(1,before-30)}}}};}};
let olderLoads=0;global._loadOlderMessages=async()=>{{olderLoads++;global._messagesTruncated=false;global._oldestIdx=0;}};
let summaryRequests=0;global.fetch=async()=>{{summaryRequests++;throw new Error('Summary refresh must remain manual');}};
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'message_projection.js'))},'utf8'));
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'session-dashboard.js'))},'utf8'));
setTimeout(()=>{{
  syncSessionDashboard();
  const button=element('sessionDashboardLoadEarlier');
  const before={{hidden:button.hidden,disabled:button.disabled,label:button.textContent,prompt:element('sessionDashboardInstruction').innerHTML}};
  button.listeners.click();
  setTimeout(()=>process.stdout.write(JSON.stringify({{before,afterHidden:button.hidden,olderLoads,historyRequests,summaryRequests}})),10);
}},30);
"""
    result = subprocess.run([node, "-e", harness], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload["before"] == {
        "hidden": False,
        "disabled": False,
        "label": "Earlier turns (151 older messages)",
        "prompt": "No prompt is available yet.",
    }
    assert payload["afterHidden"] is True
    assert payload["olderLoads"] == 1
    assert len(payload["historyRequests"]) == 4
    assert payload["summaryRequests"] == 0


def test_automatic_last_prompt_hydration_is_bounded_before_manual_load():
    assert "const PROMPT_EVIDENCE_MAX_PAGES=4;" in DASHBOARD
    assert "while(before>0&&!text&&pages<PROMPT_EVIDENCE_MAX_PAGES)" in DASHBOARD


def test_high_signal_never_promotes_continue_now_control_to_last_prompt():
    node = shutil.which("node")
    assert node is not None
    harness = f"""
const fs=require('fs');const vm=require('vm');const elements=new Map();
function element(id){{if(!elements.has(id))elements.set(id,{{id,hidden:false,textContent:'',innerHTML:'',dataset:{{}},disabled:false,addEventListener(){{}},setAttribute(){{}},removeAttribute(){{}}}});return elements.get(id);}}
global.window=global;global.document={{readyState:'complete',documentElement:{{dataset:{{sessionView:'dashboard'}}}},getElementById:element,addEventListener(){{}}}};
global.location={{href:'https://device.example/hermesUI/session/session-1'}};global.history={{state:null,replaceState(){{}}}};global.localStorage={{getItem(){{return null;}},setItem(){{}}}};
const continuation='[System: Continue now. Execute the required tool calls and only send your final answer after completing the task.]';
global.S={{session:{{session_id:'session-1'}},messages:[
  {{role:'user',content:'[Workspace::v1: /tmp]\\nPlease reconcile the client list.',id:'u1'}},
  {{role:'user',content:continuation,id:'control'}},
  {{role:'assistant',content:'The client list is reconciled.',id:'final',finish_reason:'stop'}},
],busy:false,activeStreamId:null}};
global.msgContent=m=>String(m&&m.content||'');global.renderMd=s=>String(s||'');global._stripWorkspaceDisplayPrefix=s=>String(s||'').replace(/^\\s*\\[Workspace[^\\]]*\\]\\s*/i,'').trim();global._stripAttachedFilesMarkerForDisplay=s=>String(s||'');global._messageIsRenderable=m=>!!(m&&m.role!=='tool'&&m.content);global._isContextCompactionMessage=()=>false;global._isPreservedCompressionTaskListMessage=()=>false;global._isRecoveryControlMessage=m=>String(m&&m.content||'')===continuation;global.INFLIGHT={{}};global.requestAnimationFrame=cb=>{{cb();return 1;}};global.queueMicrotask=cb=>cb();global._messagesTruncated=false;global._oldestIdx=0;global.fetch=async()=>{{throw new Error('manual summaries must not run');}};
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'message_projection.js'))},'utf8'));
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'session-dashboard.js'))},'utf8'));
setTimeout(()=>{{syncSessionDashboard();process.stdout.write(JSON.stringify({{prompt:element('sessionDashboardInstruction').innerHTML,result:element('sessionDashboardCompleted').innerHTML}}));}},20);
"""
    result = subprocess.run([node, "-e", harness], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload == {
        "prompt": "Please reconcile the client list.",
        "result": "The client list is reconciled.",
    }


def test_continue_now_control_classifier_is_exact_in_loaded_and_live_paths():
    node = shutil.which("node")
    assert node is not None
    exact = "[System: Continue now. Execute the required tool calls and only send your final answer after completing the task.]"
    cases = [exact, f"User said: {exact}", "[System: Continue now.]"]

    def extract_function(source: str, name: str) -> str:
        start = source.index(f"function {name}(")
        brace = source.index("{", start)
        depth = 0
        for index in range(brace, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[start:index + 1]
        raise AssertionError(f"{name} body not closed")

    classifiers = [
        ((ROOT / "static" / "ui.js").read_text(encoding="utf-8"), "_isRecoveryControlMessageText"),
        ((ROOT / "static" / "messages.js").read_text(encoding="utf-8"), "_streamRecoveryControlMessageText"),
    ]
    for source, name in classifiers:
        script = (
            extract_function(source, name)
            + "\nconst cases=JSON.parse(process.argv[1]);"
            + f"process.stdout.write(JSON.stringify(cases.map({name})));"
        )
        result = subprocess.run(
            [node, "-e", script, json.dumps(cases)],
            check=True,
            capture_output=True,
            text=True,
        )
        assert json.loads(result.stdout) == [True, False, False]


def test_linked_process_wakeup_promotes_direct_completion_to_high_signal_result():
    node = shutil.which("node")
    assert node is not None
    harness = f"""
const fs=require('fs');const vm=require('vm');const elements=new Map();
function element(id){{if(!elements.has(id))elements.set(id,{{id,hidden:false,textContent:'',innerHTML:'',dataset:{{}},disabled:false,attrs:{{}},addEventListener(){{}},setAttribute(name,value){{this.attrs[name]=String(value);}},removeAttribute(name){{delete this.attrs[name];}}}});return elements.get(id);}}
global.window=global;global.document={{readyState:'complete',documentElement:{{dataset:{{sessionView:'dashboard'}}}},getElementById:element,addEventListener(){{}}}};
global.location={{href:'https://device.example/hermesUI/session/session-1'}};global.history={{state:null,replaceState(){{}}}};global.localStorage={{getItem(){{return null;}},setItem(){{}}}};
global.S={{session:{{session_id:'session-1'}},messages:[
  {{role:'user',content:'Run the long verification.',id:'u1'}},
  {{role:'assistant',content:'',tool_calls:[{{function:{{name:'terminal'}}}}],finish_reason:'tool_calls'}},
  {{role:'tool',content:'Started background process proc_linked_1.'}},
  {{role:'assistant',content:'Verification is still running.',finish_reason:'stop'}},
  {{role:'user',content:'[IMPORTANT: Background process proc_linked_1 completed (exit_code=0).]',_source:'process_wakeup',_wakeup_meta:{{task_id:'proc_linked_1'}}}},
  {{role:'assistant',content:'Verification passed and the change is live.',finish_reason:'stop'}},
],busy:false,activeStreamId:null}};
global.msgContent=m=>String(m&&m.content||'');global.renderMd=s=>String(s||'');global._stripWorkspaceDisplayPrefix=s=>String(s||'').trim();global._stripAttachedFilesMarkerForDisplay=s=>String(s||'');global._messageIsRenderable=m=>!!(m&&m.role!=='tool'&&(m.content||(Array.isArray(m.tool_calls)&&m.tool_calls.length)));global._isContextCompactionMessage=()=>false;global._isPreservedCompressionTaskListMessage=()=>false;global._isRecoveryControlMessage=()=>false;global.INFLIGHT={{}};global.requestAnimationFrame=cb=>{{cb();return 1;}};global.queueMicrotask=cb=>cb();global._messagesTruncated=false;global._oldestIdx=0;global.fetch=async()=>{{throw new Error('manual summaries must not run');}};
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'message_projection.js'))},'utf8'));
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'session-dashboard.js'))},'utf8'));
setTimeout(()=>{{syncSessionDashboard();process.stdout.write(JSON.stringify({{prompt:element('sessionDashboardInstruction').innerHTML,result:element('sessionDashboardCompleted').innerHTML}}));}},20);
"""
    result = subprocess.run([node, "-e", harness], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == {
        "prompt": "Run the long verification.",
        "result": "Verification passed and the change is live.",
    }


def test_linked_direct_completion_is_available_to_manual_status_summary():
    node = shutil.which("node")
    assert node is not None
    harness = f"""
const fs=require('fs');const vm=require('vm');const elements=new Map();
function element(id){{if(!elements.has(id))elements.set(id,{{id,hidden:false,textContent:'',innerHTML:'',dataset:{{}},disabled:false,attrs:{{}},listeners:{{}},addEventListener(name,fn){{this.listeners[name]=fn;}},setAttribute(name,value){{this.attrs[name]=String(value);}},removeAttribute(name){{delete this.attrs[name];}}}});return elements.get(id);}}
global.window=global;global.document={{readyState:'complete',documentElement:{{dataset:{{sessionView:'dashboard'}}}},getElementById:element,addEventListener(){{}}}};
global.location={{href:'https://device.example/hermesUI/session/session-1'}};global.history={{state:null,replaceState(){{}}}};global.localStorage={{getItem(){{return null;}},setItem(){{}}}};
global.S={{session:{{session_id:'session-1'}},messages:[
  {{role:'user',content:'Verify the contact export.',id:'u1'}},
  {{role:'assistant',content:'',id:'start',tool_calls:[{{function:{{name:'terminal'}}}}],finish_reason:'tool_calls'}},
  {{role:'tool',content:'Background process proc_linked_2 started.',id:'started'}},
  {{role:'assistant',content:'Waiting for the export.',id:'waiting',finish_reason:'stop'}},
  {{role:'user',content:'[IMPORTANT: Background process proc_linked_2 completed (exit_code=0).]',_source:'process_wakeup',_wakeup_meta:{{task_id:'proc_linked_2'}},id:'wakeup'}},
  {{role:'assistant',content:'3,486 contacts.',id:'final',finish_reason:'stop'}},
],busy:false,activeStreamId:null}};
global.msgContent=m=>String(m&&m.content||'');global.renderMd=s=>String(s||'');global._stripWorkspaceDisplayPrefix=s=>String(s||'').trim();global._stripAttachedFilesMarkerForDisplay=s=>String(s||'');global._messageIsRenderable=m=>!!(m&&m.role!=='tool'&&(m.content||(Array.isArray(m.tool_calls)&&m.tool_calls.length)));global._isContextCompactionMessage=()=>false;global._isPreservedCompressionTaskListMessage=()=>false;global._isRecoveryControlMessage=()=>false;global.INFLIGHT={{}};global.requestAnimationFrame=cb=>{{cb();return 1;}};global.queueMicrotask=cb=>cb();global._messagesTruncated=false;global._oldestIdx=0;
const requests=[];global.fetch=async(_url,opts)=>{{const body=JSON.parse(opts.body);requests.push(body);return {{ok:true,status:200,json:async()=>({{ok:true,kind:body.kind,summary:'Current status.',provider:'test',model:'test'}})}};}};
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'message_projection.js'))},'utf8'));
vm.runInThisContext(fs.readFileSync({json.dumps(str(ROOT / 'static' / 'session-dashboard.js'))},'utf8'));
setTimeout(async()=>{{await element('sessionDashboardRefresh').listeners.click();setTimeout(()=>process.stdout.write(JSON.stringify(requests)),10);}},20);
"""
    result = subprocess.run([node, "-e", harness], check=True, capture_output=True, text=True)
    requests = json.loads(result.stdout)
    status_request = next(request for request in requests if request["kind"] == "status")
    evidence = json.dumps(status_request)
    assert "3,486 contacts." in evidence
    assert "Background process proc_linked_2 completed" not in evidence
