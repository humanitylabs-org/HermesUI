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
        [str(NODE), "-e", script, str(PROJECTION), str(SESSIONS)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
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


def test_mixed_version_tail_pages_past_detached_serialized_multimodal_shadow():
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
global.msgContent=message=>{
  const raw=String(message&&message.content||'');
  if(raw.startsWith('json:')){
    const parts=JSON.parse(raw.slice(5));
    return parts.filter(part=>part.type==='text').map(part=>part.text||'').join('');
  }
  return raw;
};
global._serializedStructuredMessageContent=value=>{
  const raw=String(value||'');
  if(!raw.startsWith('json:')) return null;
  const parts=JSON.parse(raw.slice(5));
  return {
    text:parts.filter(part=>part.type==='text').map(part=>part.text||'').join(''),
    hasMedia:parts.some(part=>part.type==='image_url'||part.type==='image'),
  };
};
global._isSerializedMultimodalShadow=(message,previous)=>{
  const parsed=_serializedStructuredMessageContent(message&&message.content);
  return !!(
    parsed&&parsed.hasMedia
    && previous&&Array.isArray(previous.attachments)&&previous.attachments.length
    && parsed.text===msgContent(previous)
    && Math.abs(Number(message.timestamp)-Number(previous.timestamp))<=10
  );
};
global._messageIsRenderable=message=>!!(message&&message.role!=='tool'&&(message.content||(message.tool_calls||[]).length));
global._isContextCompactionMessage=()=>false;
global._isPreservedCompressionTaskListMessage=()=>false;
global._isRecoveryControlMessage=()=>false;
eval(fs.readFileSync(process.argv[1],'utf8'));
global._MSG_LIMIT_MAX=500;
eval('var _LATEST_TURN_PAGE_MAX=50;'+extractFunc('_initialTailNeedsHumanTurn')+'async '+extractFunc('_expandInitialTailToLatestHumanTurn')+';global.expandTail=_expandInitialTailToLatestHumanTurn;');
const shadow={
  role:'user',
  content:'json:[{"type":"text","text":"Inspect this screenshot."},{"type":"image_url","image_url":{"url":"data:image/png;base64,AAAA"}}]',
  timestamp:100,
};
const tail=[shadow];
for(let index=0;index<13;index++) tail.push({role:'assistant',content:'',tool_calls:[{id:'call_'+index}],finish_reason:'tool_calls'});
tail.push({role:'assistant',content:'Done.',finish_reason:'stop'});
const initial={session:{session_id:'multimodal',_messages_truncated:true,_messages_offset:1,_msg_limit_max:500,messages:tail}};
const requests=[];
global.api=async url=>{
  requests.push(url);
  return {session:{
    session_id:'multimodal',_messages_truncated:false,_messages_offset:0,_msg_limit_max:500,
    messages:[{role:'user',content:'Inspect this screenshot.',attachments:[{name:'shot.png'}],timestamp:100}],
  }};
};
(async()=>{
  const expanded=await expandTail('multimodal',initial,()=>true);
  const entries=HermesMessageProjection.project(expanded.session.messages);
  const humans=entries.filter(entry=>entry.visible&&entry.semanticType==='human_prompt');
  process.stdout.write(JSON.stringify({
    requests,
    humans:humans.map(entry=>({text:msgContent(entry.message),attachments:(entry.message.attachments||[]).length})),
    serialized:JSON.stringify(expanded.session.messages),
  }));
})().catch(error=>{console.error(error);process.exit(1);});
"""
    payload = _run_node(script)
    assert len(payload["requests"]) == 1
    assert payload["humans"] == [{"text": "Inspect this screenshot.", "attachments": 1}]
    assert "base64" not in payload["serialized"]


def test_mixed_version_compaction_preserves_sanitized_background_semantics():
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
eval('var _LATEST_TURN_PAGE_MAX=50;'+extractFunc('_initialTailNeedsHumanTurn')+'async '+extractFunc('_expandInitialTailToLatestHumanTurn')+';global.expandTail=_expandInitialTailToLatestHumanTurn;');

async function runIndependent(){
  const initial={session:{session_id:'independent',_messages_truncated:true,_messages_offset:3,_msg_limit_max:500,messages:[
    {role:'assistant',content:'Independent QA found one blocker.',finish_reason:'stop'},
  ]}};
  global.api=async()=>({session:{session_id:'independent',_messages_truncated:false,_messages_offset:0,_msg_limit_max:500,messages:[
    {role:'user',content:'Ship the transcript fix.'},
    {role:'assistant',content:'The transcript fix is live.',finish_reason:'stop'},
    {role:'user',content:'[Workspace::v1: /private]\n[ASYNC DELEGATION BATCH COMPLETE — deleg_secret]\nraw orchestration payload'},
  ]}});
  return expandTail('independent',initial,()=>true);
}

async function runLinked(){
  const initial={session:{session_id:'linked',_messages_truncated:true,_messages_offset:4,_msg_limit_max:500,messages:[
    {role:'assistant',content:'The export is complete.',finish_reason:'stop'},
  ]}};
  global.api=async()=>({session:{session_id:'linked',_messages_truncated:false,_messages_offset:0,_msg_limit_max:500,messages:[
    {role:'user',content:'Export the verified contacts.'},
    {role:'assistant',content:'The export is still running.',finish_reason:'stop'},
    {role:'tool',content:'Background process proc_linked started.'},
    {role:'user',content:'[IMPORTANT: Background process proc_linked completed (exit_code=0).]',_source:'process_wakeup',_wakeup_meta:{task_id:'proc_linked'}},
  ]}});
  return expandTail('linked',initial,()=>true);
}

(async()=>{
  const independent=await runIndependent();
  const linked=await runLinked();
  const summarize=data=>{
    const messages=data.session.messages;
    const entries=HermesMessageProjection.project(messages);
    return {
      visible:entries.filter(entry=>entry.visible).map(entry=>({type:entry.semanticType,text:String(entry.message.content||'')})),
      controls:messages.filter(message=>message&&message._display_semantic_control).map(message=>({
        source:message._source,
        content:message.content,
        resumes:message._display_resumes_human_turn,
      })),
      serialized:JSON.stringify(messages),
    };
  };
  process.stdout.write(JSON.stringify({independent:summarize(independent),linked:summarize(linked)}));
})().catch(error=>{console.error(error);process.exit(1);});
"""
    payload = _run_node(script)
    assert payload["independent"]["visible"] == [
        {"type": "human_prompt", "text": "Ship the transcript fix."},
        {"type": "assistant_final", "text": "The transcript fix is live."},
        {"type": "async_update", "text": "Independent QA found one blocker."},
    ]
    assert payload["independent"]["controls"] == [
        {"source": "process_wakeup", "content": "", "resumes": False}
    ]
    assert "raw orchestration payload" not in payload["independent"]["serialized"]
    assert "/private" not in payload["independent"]["serialized"]

    assert payload["linked"]["visible"][-1] == {
        "type": "assistant_final",
        "text": "The export is complete.",
    }
    assert payload["linked"]["controls"] == [
        {"source": "process_wakeup", "content": "", "resumes": True}
    ]
    assert "proc_linked completed" not in payload["linked"]["serialized"]
