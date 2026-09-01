"""Turn-aware initial transcript loading and lazy work-gap regression coverage."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from api.routes import (
    _filter_tool_calls_for_projected_messages,
    _latest_human_turn_projection_for_display,
)
from api import routes as routes_api


ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "static" / "ui.js").read_text(encoding="utf-8")
SESSIONS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
COMMANDS = (ROOT / "static" / "commands.js").read_text(encoding="utf-8")
PROJECTION = ROOT / "static" / "message_projection.js"
NODE = shutil.which("node")


def _function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    quote = None
    escaped = False
    for index in range(brace, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ("'", '"', "`"):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"function did not close: {signature}")


def _section(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def test_cold_and_warm_initial_requests_use_turn_aware_contract():
    assert SESSIONS.count("latest_human_turn=1") >= 2
    expand = _function_body(SESSIONS, "async function _expandInitialTailToLatestHumanTurn")
    assert "session._latest_human_turn_projected" in expand


def test_gap_rows_are_renderable_interim_controls_not_final_answers():
    assert NODE is not None
    script = r"""
const fs=require('fs');
global.window=global;
global.msgContent=message=>String(message&&message.content||'');
global._messageIsRenderable=message=>!!(message&&message._latest_turn_gap)||!!(message&&message.role!=='tool'&&message.content);
global._isContextCompactionMessage=()=>false;
global._isPreservedCompressionTaskListMessage=()=>false;
global._isRecoveryControlMessage=()=>false;
eval(fs.readFileSync(process.argv[1],'utf8'));
const entries=HermesMessageProjection.visible([
  {role:'user',content:'Ship it',_display_source_index:10},
  {role:'assistant',content:'',_latest_turn_gap:{start_index:11,end_index:800,omitted_records:789}},
  {role:'assistant',content:'Live and verified',_display_source_index:800,finish_reason:'stop'},
]);
process.stdout.write(JSON.stringify(entries.map(entry=>({type:entry.semanticType,visible:entry.visible}))));
"""
    result = subprocess.run(
        [NODE, "-e", script, str(PROJECTION)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert json.loads(result.stdout) == [
        {"type": "human_prompt", "visible": True},
        {"type": "assistant_interim", "visible": True},
        {"type": "assistant_final", "visible": True},
    ]


def test_projected_rows_preserve_absolute_edit_and_fork_indices():
    session_index = _function_body(UI, "function _messageSessionIndexForRawIdx")
    raw_index = _function_body(UI, "function _messageRawIdxForSessionIndex")
    assert "_display_source_index" in session_index
    assert "_display_source_index" in raw_index
    assert "source!==null" in session_index
    assert "return null" in session_index


def test_projected_edit_regenerate_and_fork_send_absolute_keep_counts():
    assert NODE is not None
    definitions = "\n".join(
        [
            _section(UI, "function _messageSessionIndexBase", "function _messageVirtualScrollTopForVisibleIdx"),
            _section(UI, "async function submitEdit", "async function regenerateResponse"),
            _section(UI, "async function regenerateResponse", "// postProcessRenderedMessages"),
            _section(COMMANDS, "async function forkFromMessage", "let _skillCommandCache"),
        ]
    )
    script = r"""
global.S={
  session:{session_id:'projected',message_revision:'rev-projected'},busy:false,
  messages:[
    {role:'user',content:'Ship it',_display_source_index:100},
    {role:'assistant',content:'',_latest_turn_gap:{start_index:101,end_index:1800}},
    {role:'assistant',content:'Verified',_display_source_index:1800},
  ],
};
global._oldestIdx=100;
global._messagesTruncated=true;
global._deliberateSessionModelPick=()=>null;
global._ensureAllMessagesLoaded=async()=>{
  S.messages=Array.from({length:1802},(_,index)=>({
    role:index===100?'user':'assistant',
    content:index===100?'Ship it':(index===1800?'Verified':''),
  }));
  _oldestIdx=0;
  _messagesTruncated=false;
};
global._reArmRecoveryPick=()=>{};
global.renderMessages=()=>{};
global.send=async()=>{};
global.$=()=>({value:''});
global.msgContent=message=>String(message&&message.content||'');
global._isReadOnlySession=()=>false;
global._isBranchableReadOnlySession=()=>true;
global.showToast=()=>{};
global.loadSession=async()=>{};
global.renderSessionList=async()=>{};
global.t=key=>key;
const calls=[];
global.api=async(path,options={})=>{
  calls.push({path,body:options.body?JSON.parse(options.body):null});
  return path==='/api/session/branch'?{session_id:'forked'}:{};
};
eval(process.argv[1]);
(async()=>{
  await submitEdit(0,'Edited prompt');
  S.messages=[
    {role:'user',content:'Ship it',_display_source_index:100},
    {role:'assistant',content:'',_latest_turn_gap:{start_index:101,end_index:1800}},
    {role:'assistant',content:'Verified',_display_source_index:1800},
  ];
  _oldestIdx=100;
  _messagesTruncated=true;
  await regenerateResponse({closest:()=>({dataset:{msgIdx:'2'}})});
  S.messages=[
    {role:'user',content:'Ship it',_display_source_index:100},
    {role:'assistant',content:'',_latest_turn_gap:{start_index:101,end_index:1800}},
    {role:'assistant',content:'Verified',_display_source_index:1800},
  ];
  _oldestIdx=100;
  _messagesTruncated=true;
  await forkFromMessage(3);
  S.messages=[
    {role:'user',content:'Ship it',_display_source_index:100},
    {role:'assistant',content:'Live answer',_live:true},
  ];
  const unindexedProjected=_messageSessionIndexForRawIdx(1);
  process.stdout.write(JSON.stringify({calls,unindexedProjected}));
})().catch(error=>{console.error(error);process.exit(1)});
"""
    result = subprocess.run(
        [NODE, "-e", script, definitions],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = json.loads(result.stdout)
    assert [call["body"]["keep_count"] for call in output["calls"]] == [100, 1800, 1801]
    assert [call["body"].get("expected_message_revision") for call in output["calls"][:2]] == [
        "rev-projected",
        "rev-projected",
    ]
    assert output["unindexedProjected"] is None


def test_work_gap_is_collapsed_and_loads_omitted_range_on_demand():
    assert "latest-turn-gap-card" in UI
    assert "Work details" in UI
    assert "async function _loadLatestTurnGap" in UI
    loader = _function_body(UI, "async function _loadLatestTurnGap")
    assert "msg_before=${cursor}" in loader
    assert "msg_limit=${pageLimit}" in loader
    assert "gap.start_index" in loader
    assert "gap.end_index" in loader
    assert "_display_source_index" in loader
    assert "loaded=bounded.concat(loaded)" in loader
    assert "latest-turn-gap-body" in UI
    assert "latest-turn-gap-body" in CSS


def test_lazy_work_gap_renders_session_tools_and_sanitized_mixed_prose():
    assert NODE is not None
    loader = _section(UI, "async function _loadLatestTurnGap", "function _onLatestTurnGapToggle")
    script = r"""
const body={
  textContent:'',innerHTML:'',children:[],
  appendChild(node){this.children.push(...(node.children||[node]));},
};
const details={
  open:true,
  getAttribute:name=>name==='data-raw-idx'?'0':'',
  querySelector:selector=>selector==='.latest-turn-gap-body'?body:null,
};
global.S={
  session:{session_id:'session',_msg_limit_max:500},
  messages:[{role:'assistant',_latest_turn_gap:{start_index:10,end_index:12}}],
};
global.document={
  createDocumentFragment:()=>({children:[],appendChild(node){this.children.push(node);}}),
  createElement:()=>({className:'',textContent:''}),
};
global._assistantVisibleContentForReasoningCompare=message=>{
  if(String(message.content||'').includes('Visible prose')) return 'Visible prose';
  return '';
};
global.api=async()=>({session:{
  _messages_offset:10,
  messages:[
    {role:'assistant',content:[{type:'tool_use',id:'use_3',name:'terminal'}]},
    {role:'assistant',content:'<think>secret</think>Visible prose'},
  ],
  tool_calls:[
    {assistant_msg_idx:0,tool_use_id:'use_1',name:'terminal'},
    {assistant_msg_idx:0,tool_use_id:'use_2',name:'terminal'},
  ],
}});
eval(process.argv[1]);
(async()=>{
  await _loadLatestTurnGap(details);
  process.stdout.write(JSON.stringify(body.children.map(node=>({className:node.className,text:node.textContent}))));
})().catch(error=>{console.error(error);process.exit(1)});
"""
    result = subprocess.run(
        [str(NODE), "-e", script, loader],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    rows = json.loads(result.stdout)
    assert rows == [
        {"className": "latest-turn-gap-tool", "text": "terminal"},
        {"className": "latest-turn-gap-tool", "text": "terminal"},
        {"className": "latest-turn-gap-tool", "text": "terminal"},
        {"className": "latest-turn-gap-prose", "text": "Visible prose"},
    ]
    assert "secret" not in json.dumps(rows)


def _tool_heavy_turn(tool_count: int = 900) -> list[dict]:
    messages: list[dict] = [
        {"role": "user", "content": "Please ship the exact fix.", "timestamp": 1}
    ]
    for index in range(tool_count):
        tool_id = f"call_{index}"
        messages.extend(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": tool_id,
                            "type": "function",
                            "function": {"name": "terminal", "arguments": "{}"},
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
                {"role": "tool", "tool_call_id": tool_id, "content": "ok"},
            ]
        )
    messages.append(
        {"role": "assistant", "content": "The fix is live and verified.", "finish_reason": "stop"}
    )
    return messages


def test_server_projection_recovers_prompt_beyond_four_hundred_eighty_visible_rows():
    messages = _tool_heavy_turn()

    projected, offset = _latest_human_turn_projection_for_display(messages, msg_limit=6)

    assert offset == 0
    assert projected[0]["content"] == "Please ship the exact fix."
    assert projected[-1]["content"] == "The fix is live and verified."
    assert projected[-1]["_display_source_index"] == len(messages) - 1
    gaps = [message["_latest_turn_gap"] for message in projected if message.get("_latest_turn_gap")]
    assert len(gaps) == 1
    assert gaps[0]["omitted_records"] > 1700
    assert gaps[0]["omitted_renderable"] > 850
    assert len(projected) <= 14


def test_sparse_source_zero_projection_is_still_marked_truncated():
    messages = _tool_heavy_turn()
    projected, offset = _latest_human_turn_projection_for_display(messages, msg_limit=6)
    helper = getattr(routes_api, "_message_window_is_truncated_for_display", None)

    assert helper is not None
    assert offset == 0
    assert any(message.get("_latest_turn_gap") for message in projected)
    assert helper(projected, offset, load_messages=True, msg_limit=6) is True


def test_sparse_source_zero_projection_requires_full_load_without_fake_earlier_turns():
    sparse_start = SESSIONS.index("function _loadedMessageWindowIsSparse")
    sparse_end = SESSIONS.index("async function _ensureAllMessagesLoaded", sparse_start)
    script = r"""
global._oldestIdx=0;
global._messagesTruncated=false;
global.S={messages:[
  {role:'user',content:'Ship it',_display_source_index:0},
  {role:'assistant',content:'',_latest_turn_gap:{start_index:1,end_index:1800}},
  {role:'assistant',content:'Old final',_display_source_index:1800},
]};
eval(process.argv[1]);
process.stdout.write(JSON.stringify({sparse:_loadedMessageWindowIsSparse(),needs:_messageHistoryNeedsFullLoad()}));
"""
    result = subprocess.run(
        [str(NODE), "-e", script, SESSIONS[sparse_start:sparse_end]],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert json.loads(result.stdout) == {"sparse": True, "needs": True}
    assert "&& Number(_oldestIdx)>0" in UI


def test_linked_background_completion_survives_more_than_six_hundred_records():
    messages: list[dict] = [
        {"role": "user", "content": "Run validation."},
        {"role": "tool", "content": "Background process proc_long started."},
    ]
    for index in range(300):
        call_id = f"call_noise_{index}"
        messages.extend(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": call_id, "function": {"name": "terminal"}}],
                    "finish_reason": "tool_calls",
                },
                {"role": "tool", "tool_call_id": call_id, "content": "ok"},
            ]
        )
    messages.extend(
        [
            {"role": "assistant", "content": "Validation is still running."},
            {
                "role": "user",
                "content": "[IMPORTANT: Background process proc_long completed]",
                "_source": "process_wakeup",
            },
            {
                "role": "assistant",
                "content": "Validation passed.",
                "_wakeup_meta": {"process_id": "proc_long"},
                "finish_reason": "stop",
            },
        ]
    )

    projected, _ = _latest_human_turn_projection_for_display(messages, msg_limit=2)
    assert not any(message.get("_display_semantic_control") for message in projected)
    final_message = next(message for message in projected if message.get("content") == "Validation passed.")
    assert final_message["_display_semantic_type"] == "assistant_final"
    assert final_message["_display_background_update"] is False

    script = r"""
const fs=require('fs');
global.window=global;
global.msgContent=message=>String(message&&message.content||'');
global._messageIsRenderable=message=>!!(message&&message._latest_turn_gap)||!!(message&&message.role!=='tool'&&(message.content||(message.tool_calls||[]).length));
global._isContextCompactionMessage=()=>false;
global._isPreservedCompressionTaskListMessage=()=>false;
global._isRecoveryControlMessage=()=>false;
eval(fs.readFileSync(process.argv[1],'utf8'));
const source=JSON.parse(process.argv[2]);
const final=HermesMessageProjection.project(source).find(entry=>String(entry.message&&entry.message.content||'')==='Validation passed.');
process.stdout.write(JSON.stringify({type:final.semanticType,background:final.backgroundUpdate}));
"""
    result = subprocess.run(
        [str(NODE), "-e", script, str(PROJECTION), json.dumps(messages)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert json.loads(result.stdout) == {"type": "assistant_final", "background": False}


def test_many_linked_background_controls_stay_linear_and_bounded():
    messages: list[dict] = [{"role": "user", "content": "Run all validations."}]
    for index in range(4000):
        task_id = f"proc_{index}"
        messages.extend(
            [
                {"role": "tool", "content": f"Background process {task_id} started."},
                {"role": "assistant", "content": "Validation is still running."},
                {
                    "role": "user",
                    "content": f"[IMPORTANT: Background process {task_id} completed]",
                    "_source": "process_wakeup",
                },
            ]
        )
    messages.append({"role": "assistant", "content": "Validation passed.", "finish_reason": "stop"})

    started = time.perf_counter()
    projected, _ = _latest_human_turn_projection_for_display(messages, msg_limit=6)
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert len(projected) <= 20
    assert len(json.dumps(projected)) < 50_000
    assert not any(message.get("_display_semantic_control") for message in projected)


def test_server_projection_keeps_primary_final_before_later_updates():
    messages = [
        {"role": "user", "content": "Run the release."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_release",
                    "type": "function",
                    "function": {"name": "terminal", "arguments": "{}"},
                }
            ],
            "finish_reason": "tool_calls",
        },
        {"role": "tool", "tool_call_id": "call_release", "content": "ok"},
        {"role": "assistant", "content": "Release verified.", "finish_reason": "stop"},
        {
            "role": "user",
            "content": "[ASYNC DELEGATION BATCH COMPLETE — deleg_review]",
            "_source": "async_delegation",
        },
        {"role": "assistant", "content": "Independent review passed.", "finish_reason": "stop"},
    ]

    projected, offset = _latest_human_turn_projection_for_display(messages, msg_limit=2)

    assert offset == 0
    assert projected[0]["content"] == "Run the release."
    assert any(message.get("content") == "Release verified." for message in projected)
    assert projected[-1]["content"] == "Independent review passed."
    assert not any(message.get("_display_semantic_control") for message in projected)
    assert "ASYNC DELEGATION" not in json.dumps(projected)
    primary_message = next(message for message in projected if message.get("content") == "Release verified.")
    update_message = next(message for message in projected if message.get("content") == "Independent review passed.")
    assert primary_message["_display_semantic_type"] == "assistant_final"
    assert primary_message["_display_background_update"] is False
    assert update_message["_display_semantic_type"] == "async_update"
    assert update_message["_display_background_update"] is True

    script = r"""
const fs=require('fs');
global.window=global;
global.msgContent=message=>String(message&&message.content||'');
global._messageIsRenderable=message=>!!(message&&message._latest_turn_gap)||!!(message&&message.role!=='tool'&&message.content);
global._isContextCompactionMessage=()=>false;
global._isPreservedCompressionTaskListMessage=()=>false;
global._isRecoveryControlMessage=()=>false;
eval(fs.readFileSync(process.argv[1],'utf8'));
const entries=HermesMessageProjection.project(JSON.parse(process.argv[2]));
process.stdout.write(JSON.stringify(entries.map(entry=>({
  content:String(entry.message&&entry.message.content||''),
  type:entry.semanticType,
  background:entry.backgroundUpdate,
  visible:entry.visible,
}))));
"""
    result = subprocess.run(
        [NODE, "-e", script, str(PROJECTION), json.dumps(projected)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    entries = json.loads(result.stdout)
    primary = next(entry for entry in entries if entry["content"] == "Release verified.")
    update = next(entry for entry in entries if entry["content"] == "Independent review passed.")
    assert primary == {
        "content": "Release verified.",
        "type": "assistant_final",
        "background": False,
        "visible": True,
    }
    assert update == {
        "content": "Independent review passed.",
        "type": "async_update",
        "background": True,
        "visible": True,
    }


def test_explicit_semantics_preserve_linked_primary_resume_without_control_rows():
    messages = [
        {"role": "user", "content": "Run the long validation."},
        {"role": "assistant", "content": "Validation is still running."},
        {"role": "tool", "content": "Background process proc_1234 started."},
        {
            "role": "user",
            "content": "[IMPORTANT: Background process proc_1234 completed]",
            "_source": "process_wakeup",
        },
        {
            "role": "assistant",
            "content": "Validation passed.",
            "_wakeup_meta": {"process_id": "proc_1234"},
            "finish_reason": "stop",
        },
    ]

    projected, _ = _latest_human_turn_projection_for_display(messages, msg_limit=1)
    assert not any(message.get("_display_semantic_control") for message in projected)
    projected_final = next(message for message in projected if message.get("content") == "Validation passed.")
    assert projected_final["_display_semantic_type"] == "assistant_final"
    assert projected_final["_display_background_update"] is False

    script = r"""
const fs=require('fs');
global.window=global;
global.msgContent=message=>String(message&&message.content||'');
global._messageIsRenderable=message=>!!(message&&message._latest_turn_gap)||!!(message&&message.role!=='tool'&&message.content);
global._isContextCompactionMessage=()=>false;
global._isPreservedCompressionTaskListMessage=()=>false;
global._isRecoveryControlMessage=()=>false;
eval(fs.readFileSync(process.argv[1],'utf8'));
const entries=HermesMessageProjection.project(JSON.parse(process.argv[2]));
const final=entries.find(entry=>String(entry.message&&entry.message.content||'')==='Validation passed.');
process.stdout.write(JSON.stringify({type:final.semanticType,background:final.backgroundUpdate,visible:final.visible}));
"""
    result = subprocess.run(
        [str(NODE), "-e", script, str(PROJECTION), json.dumps(projected)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert json.loads(result.stdout) == {
        "type": "assistant_final",
        "background": False,
        "visible": True,
    }


def test_projection_ignores_empty_recovery_rows_and_nonvisible_raw_holes():
    messages = [
        {"role": "user", "content": "Finish this run."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_finish",
                    "type": "function",
                    "function": {"name": "terminal", "arguments": "{}"},
                }
            ],
            "finish_reason": "tool_calls",
        },
        {"role": "tool", "tool_call_id": "call_finish", "content": "ok"},
        {"role": "assistant", "content": "Finished and verified.", "finish_reason": "stop"},
        {"role": "tool", "tool_call_id": "orphan", "content": "hidden"},
        {
            "role": "assistant",
            "content": "",
            "reasoning": "",
            "_recovered_from_run_journal": True,
        },
    ]

    projected, offset = _latest_human_turn_projection_for_display(messages, msg_limit=1)

    assert offset == 0
    assert projected[-1]["content"] == "Finished and verified."
    gaps = [message["_latest_turn_gap"] for message in projected if message.get("_latest_turn_gap")]
    assert len(gaps) == 1
    assert gaps[0]["start_index"] == 1
    assert gaps[0]["end_index"] == 3


def test_projection_anchors_attachment_prompt_not_serialized_multimodal_shadow():
    attachment = "/home/oscar/.hermes/nesquena-webui/attachments/session/screenshot.png"
    prompt = {
        "role": "user",
        "content": (
            "[Workspace::v1: /home/oscar/workspace]\n"
            "Inspect this screenshot.\n\n"
            f"[Attached files: {attachment}]"
        ),
        "attachments": ["screenshot.png"],
        "timestamp": 100,
    }
    shadow = {
        "role": "user",
        "content": "json:" + json.dumps(
            [
                {"type": "text", "text": "Inspect this screenshot."},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AAAA"},
                },
            ]
        ),
        "timestamp": 101,
    }
    messages = [
        prompt,
        shadow,
        {"role": "assistant", "content": "I inspected it.", "finish_reason": "stop"},
    ]

    projected, offset = _latest_human_turn_projection_for_display(messages, msg_limit=1)

    assert offset == 0
    assert projected[0]["attachments"] == ["screenshot.png"]
    assert projected[0]["_display_source_index"] == 0
    assert projected[-1]["content"] == "I inspected it."
    assert all(not str(message.get("content") or "").startswith("json:") for message in projected)
    assert all(message.get("_display_source_index") != 1 for message in projected)


def test_projected_tool_calls_keep_original_assistant_mapping():
    messages = _tool_heavy_turn(tool_count=8)
    projected, _ = _latest_human_turn_projection_for_display(messages, msg_limit=2)
    calls = [
        {"assistant_msg_idx": 15, "name": "terminal"},
        {"assistant_msg_idx": 1, "name": "terminal"},
    ]

    filtered = _filter_tool_calls_for_projected_messages(calls, projected)

    assert len(filtered) == 1
    assert filtered[0]["name"] == "terminal"
    mapped = projected[filtered[0]["assistant_msg_idx"]]
    assert mapped["_display_source_index"] == 15
