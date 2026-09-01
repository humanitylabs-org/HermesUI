"""Turn-aware initial transcript loading and lazy work-gap regression coverage."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from api.routes import (
    _filter_tool_calls_for_projected_messages,
    _latest_human_turn_projection_for_display,
)


ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "static" / "ui.js").read_text(encoding="utf-8")
SESSIONS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
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
