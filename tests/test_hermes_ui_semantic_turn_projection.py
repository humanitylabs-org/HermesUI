import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
PROJECTION = ROOT / "static" / "message_projection.js"
SESSIONS = ROOT / "static" / "sessions.js"


def _run_node(script: str):
    assert NODE is not None
    result = subprocess.run(
        [NODE, "-e", script, str(PROJECTION), str(SESSIONS)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(result.stdout)


def test_finished_answer_survives_unlinked_wakeup_tool_activity():
    script = r"""
const fs=require('fs');
global.window=global;
global.msgContent=message=>String(message&&message.content||'');
global._messageIsRenderable=message=>!!(message&&message.role!=='tool'&&(message.content||(message.tool_calls||[]).length));
global._isContextCompactionMessage=message=>String(message&&message.content||'').startsWith('[CONTEXT COMPACTION');
global._isPreservedCompressionTaskListMessage=()=>false;
global._isRecoveryControlMessage=()=>false;
eval(fs.readFileSync(process.argv[1],'utf8'));
const messages=[
  {role:'user',content:'Ship the transcript repair.'},
  {role:'assistant',content:'',tool_calls:[{function:{name:'terminal'}}],finish_reason:'tool_calls'},
  {role:'tool',content:'DEPLOY_FINISHED'},
  {role:'assistant',content:'The transcript repair is live and verified.',finish_reason:'stop'},
  {role:'user',content:'[Workspace::v1: /home/oscar/workspace]\n[IMPORTANT: Background process proc_qa completed (exit_code=0).]'},
  {role:'assistant',content:'',tool_calls:[{function:{name:'terminal'}}],finish_reason:'tool_calls'},
  {role:'tool',content:'QA_COMPLETE'},
  {role:'assistant',content:'Independent QA reported no blockers.',finish_reason:'stop'},
  {role:'user',content:'[CONTEXT COMPACTION — reference only]'},
];
const all=HermesMessageProjection.project(messages);
const visible=all.filter(entry=>entry.visible).map(entry=>({idx:entry.rawIdx,type:entry.semanticType,bg:entry.backgroundUpdate}));
const primary=all.filter(entry=>entry.semanticType==='assistant_final').map(entry=>entry.message.content);
const controls=all.filter(entry=>entry.semanticType==='system_control').map(entry=>entry.rawIdx);
process.stdout.write(JSON.stringify({visible,primary,controls}));
"""
    payload = _run_node(script)
    assert payload["primary"] == ["The transcript repair is live and verified."]
    assert payload["visible"][-1] == {"idx": 7, "type": "async_update", "bg": True}
    assert payload["controls"] == [4, 8]


def test_linked_wakeup_can_finish_the_original_human_turn():
    script = r"""
const fs=require('fs');
global.window=global;
global.msgContent=message=>String(message&&message.content||'');
global._messageIsRenderable=message=>!!(message&&message.role!=='tool'&&(message.content||(message.tool_calls||[]).length));
global._isContextCompactionMessage=()=>false;
global._isPreservedCompressionTaskListMessage=()=>false;
global._isRecoveryControlMessage=()=>false;
eval(fs.readFileSync(process.argv[1],'utf8'));
const messages=[
  {role:'user',content:'Verify the export.'},
  {role:'assistant',content:'',tool_calls:[{function:{name:'terminal'}}],finish_reason:'tool_calls'},
  {role:'tool',content:'Background process proc_linked started.'},
  {role:'assistant',content:'Verification is still running.',finish_reason:'stop'},
  {role:'user',content:'[Workspace::v1: /home/oscar/workspace]\n[IMPORTANT: Background process proc_linked completed (exit_code=0).]'},
  {role:'assistant',content:'The export contains 3,486 verified contacts.',finish_reason:'stop'},
];
const visible=HermesMessageProjection.visible(messages).map(entry=>({text:String(entry.message.content||''),type:entry.semanticType,bg:entry.backgroundUpdate}));
process.stdout.write(JSON.stringify(visible));
"""
    payload = _run_node(script)
    assert payload[-1] == {
        "text": "The export contains 3,486 verified contacts.",
        "type": "assistant_final",
        "bg": False,
    }
    assert all(not entry["bg"] for entry in payload)


def test_workspace_prefixed_delegation_envelope_is_never_a_human_prompt():
    script = r"""
const fs=require('fs');
global.window=global;
global.msgContent=message=>String(message&&message.content||'');
global._messageIsRenderable=message=>!!(message&&message.role!=='tool'&&(message.content||(message.tool_calls||[]).length));
global._isContextCompactionMessage=()=>false;
global._isPreservedCompressionTaskListMessage=()=>false;
global._isRecoveryControlMessage=()=>false;
eval(fs.readFileSync(process.argv[1],'utf8'));
const messages=[
  {role:'user',content:'Ship the Apps page.'},
  {role:'assistant',content:'The Apps page is live.',finish_reason:'stop'},
  {role:'user',content:'[Workspace::v1: /home/oscar/workspace]\n[ASYNC DELEGATION BATCH COMPLETE — deleg_6695d6f0]\nA background fan-out finished.'},
  {role:'assistant',content:'Independent review found one blocker.',finish_reason:'stop'},
];
const all=HermesMessageProjection.project(messages);
process.stdout.write(JSON.stringify({
  visible:all.filter(entry=>entry.visible).map(entry=>({idx:entry.rawIdx,type:entry.semanticType,text:String(entry.message.content||'')})),
  controls:all.filter(entry=>entry.semanticType==='system_control').map(entry=>entry.rawIdx),
}));
"""
    payload = _run_node(script)
    assert payload["controls"] == [2]
    assert payload["visible"] == [
        {"idx": 0, "type": "human_prompt", "text": "Ship the Apps page."},
        {"idx": 1, "type": "assistant_final", "text": "The Apps page is live."},
        {"idx": 3, "type": "async_update", "text": "Independent review found one blocker."},
    ]


def test_cold_tail_expands_only_until_latest_human_prompt_is_present():
    script = r"""
const fs=require('fs');
const sessions=fs.readFileSync(process.argv[2],'utf8');
function extractFunc(name){
  const start=sessions.indexOf('function '+name);
  if(start<0) throw new Error(name+' not found');
  let brace=sessions.indexOf('{',start),depth=0;
  for(let i=brace;i<sessions.length;i++){
    if(sessions[i]==='{') depth++;
    else if(sessions[i]==='}'&&--depth===0) return sessions.slice(start,i+1);
  }
  throw new Error(name+' unterminated');
}
global.window=global;
global.msgContent=message=>String(message&&message.content||'');
global._messageIsRenderable=message=>!!(message&&message.role!=='tool'&&(message.content||(message.tool_calls||[]).length));
global._isContextCompactionMessage=()=>false;
global._isPreservedCompressionTaskListMessage=()=>false;
global._isRecoveryControlMessage=()=>false;
eval(fs.readFileSync(process.argv[1],'utf8'));
global._MSG_LIMIT_MAX=500;
const definitions='var _LATEST_TURN_PAGE_MAX=50;'+extractFunc('_initialTailNeedsHumanTurn')+'async '+extractFunc('_expandInitialTailToLatestHumanTurn')+';global.expandTail=_expandInitialTailToLatestHumanTurn;';
eval(definitions);
const initial={session:{session_id:'s1',_messages_truncated:true,_messages_offset:900,_msg_limit_max:500,messages:[
  {role:'assistant',content:'The real answer.',finish_reason:'stop'},
  {role:'user',content:'[BACKGROUND WAKEUP proc_qa]',_source:'process_wakeup'},
  {role:'assistant',content:'Later QA.',finish_reason:'stop'},
]}};
const requests=[];
global.api=async url=>{
  requests.push(url);
  const older=[{role:'user',content:'The initiating human request.'}];
  for(let index=1;index<500;index++) older.push({
    role:'assistant',
    content:'',
    tool_calls:[{id:'call_'+index,type:'function',function:{name:'tool_'+index,arguments:'{}'}}],
    finish_reason:'tool_calls',
  });
  return {session:{session_id:'s1',_messages_truncated:true,_messages_offset:400,_msg_limit_max:500,messages:older}};
};
(async()=>{
  const expanded=await expandTail('s1',initial,()=>true);
  process.stdout.write(JSON.stringify({
    requests,
    messages:expanded.session.messages.map(message=>message.content),
    projected:expanded.session._latest_human_turn_projected,
    source:expanded.session._latest_human_turn_projection_source,
    gaps:expanded.session._latest_human_turn_gap_count,
  }));
})().catch(error=>{console.error(error);process.exit(1);});
"""
    payload = _run_node(script)
    assert len(payload["requests"]) == 1
    assert "msg_limit=500" in payload["requests"][0]
    assert "msg_before=900" in payload["requests"][0]
    assert payload["messages"][0] == "The initiating human request."
    assert payload["projected"] is True
    assert payload["source"] == "client_paging"
    assert payload["gaps"] == 1


def test_cold_tail_with_only_async_updates_still_recovers_the_human_prompt():
    script = r"""
const fs=require('fs');
const sessions=fs.readFileSync(process.argv[2],'utf8');
function extractFunc(name){
  const start=sessions.indexOf('function '+name);
  if(start<0) throw new Error(name+' not found');
  let brace=sessions.indexOf('{',start),depth=0;
  for(let i=brace;i<sessions.length;i++){
    if(sessions[i]==='{') depth++;
    else if(sessions[i]==='}'&&--depth===0) return sessions.slice(start,i+1);
  }
  throw new Error(name+' unterminated');
}
global.window=global;
global.msgContent=message=>String(message&&message.content||'');
global._messageIsRenderable=message=>!!(message&&message.role!=='tool'&&(message.content||(message.tool_calls||[]).length));
global._isContextCompactionMessage=()=>false;
global._isPreservedCompressionTaskListMessage=()=>false;
global._isRecoveryControlMessage=()=>false;
eval(fs.readFileSync(process.argv[1],'utf8'));
eval(extractFunc('_initialTailNeedsHumanTurn'));
const messages=[
  {role:'user',content:'[IMPORTANT: Background process proc_review completed (exit_code=0).]',_source:'process_wakeup'},
  {role:'assistant',content:'Independent review found no blockers.',finish_reason:'stop'},
];
process.stdout.write(JSON.stringify(_initialTailNeedsHumanTurn(messages)));
"""
    assert _run_node(script) is True
