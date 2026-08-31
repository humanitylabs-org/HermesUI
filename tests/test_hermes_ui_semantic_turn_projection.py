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
  {role:'user',content:'[IMPORTANT: Background process proc_qa completed (exit_code=0).]',_source:'process_wakeup'},
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
  {role:'user',content:'[IMPORTANT: Background process proc_linked completed (exit_code=0).]',_source:'process_wakeup',_wakeup_meta:{task_id:'proc_linked'}},
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
const definitions='var _LATEST_TURN_AUTO_LIMITS=[120,480];'+extractFunc('_initialTailNeedsHumanTurn')+'async '+extractFunc('_expandInitialTailToLatestHumanTurn')+';global.expandTail=_expandInitialTailToLatestHumanTurn;';
eval(definitions);
const initial={session:{session_id:'s1',_messages_truncated:true,_msg_limit_max:500,messages:[
  {role:'assistant',content:'The real answer.',finish_reason:'stop'},
  {role:'user',content:'[BACKGROUND WAKEUP proc_qa]',_source:'process_wakeup'},
  {role:'assistant',content:'Later QA.',finish_reason:'stop'},
]}};
const requests=[];
global.api=async url=>{
  requests.push(url);
  return {session:{session_id:'s1',_messages_truncated:true,_msg_limit_max:500,messages:[
    {role:'user',content:'The initiating human request.'},
    ...initial.session.messages,
  ]}};
};
(async()=>{
  const expanded=await expandTail('s1',initial,()=>true);
  process.stdout.write(JSON.stringify({requests,messages:expanded.session.messages.map(message=>message.content)}));
})().catch(error=>{console.error(error);process.exit(1);});
"""
    payload = _run_node(script)
    assert len(payload["requests"]) == 1
    assert "msg_limit=120" in payload["requests"][0]
    assert payload["messages"][0] == "The initiating human request."
