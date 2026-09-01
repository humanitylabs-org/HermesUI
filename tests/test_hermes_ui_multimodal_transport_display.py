"""Regression coverage for serialized multimodal transport rows in Classic/High Signal."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_JS = (ROOT / "static" / "ui.js").read_text(encoding="utf-8")
PROJECTION_JS = ROOT / "static" / "message_projection.js"
NODE = shutil.which("node")


def _function_body(source: str, name: str) -> str:
    start = source.index(name)
    brace = source.index("{", start)
    depth = 0
    quote = None
    escaped = False
    template_depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if quote == "`" and char == "$" and index + 1 < len(source) and source[index + 1] == "{":
                template_depth += 1
                continue
            if char == quote and template_depth == 0:
                quote = None
            elif quote == "`" and char == "}" and template_depth:
                template_depth -= 1
            continue
        if char in ("'", '"', "`"):
            quote = char
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Function did not close: {name}")


def _between(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    return source[start_index : source.index(end, start_index)]


def _run_node(script: str) -> dict:
    assert NODE is not None
    result = subprocess.run([NODE, "-e", script], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def test_serialized_multimodal_content_exposes_only_text_and_preserves_literal_json():
    prompt = (
        "[Workspace::v1: /home/oscar/workspace]\n"
        "Remove the redundant transcript chrome.\n\n"
        "[Attached files: /home/oscar/.hermes/nesquena-webui/attachments/605b057e462e/screenshot.png]"
    )
    transport = "\x00json:" + json.dumps(
        [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,SECRET_PIXELS"}},
        ]
    )
    malformed = (
        '\x00json:[{"type":"text","text":"hello\nworld"},'
        '{"type":"image_url","image_url":{"url":"data:image/png;base64,SECRET_PIXELS"}}]'
    )
    helpers = "\n".join(
        [
            _between(UI_JS, "function _structuredMessageContentText", "function _serializedStructuredMessageContent"),
            _between(UI_JS, "function _serializedStructuredMessageContent", "function _isSerializedMultimodalShadow"),
            _between(UI_JS, "function _isSerializedMultimodalShadow", "function msgContent"),
            _between(UI_JS, "function msgContent", "function _isRecoveryControlMessageText"),
        ]
    )
    script = f"""
{helpers}
global.S={{session:{{session_id:'605b057e462e'}}}};
const transport={json.dumps(transport)};
const malformed={json.dumps(malformed)};
const literal='json:[1,2,3]';
const native=[{{type:'text',text:'native prompt'}},{{type:'image_url',image_url:{{url:'data:image/png;base64,SECRET_PIXELS'}}}}];
const parsedTransport=_serializedStructuredMessageContent(transport);
const parsedNative=_structuredMessageContentText(native);
const recovered=_serializedAttachmentMedia(parsedTransport.text,parsedTransport.media.length);
const rejected=_serializedAttachmentMedia(parsedTransport.text.replace('605b057e462e','different-session'),parsedTransport.media.length);
process.stdout.write(JSON.stringify({{
  transport:msgContent({{content:transport}}),
  malformed:msgContent({{content:malformed}}),
  literal:msgContent({{content:literal}}),
  native:msgContent({{content:native}}),
  transportMediaCount:parsedTransport.media.length,
  nativeMediaCount:parsedNative.media.length,
  recoveredCount:recovered.length,
  recoveredName:recovered[0]?.name||'',
  recoveredUsesMediaEndpoint:String(recovered[0]?.url||'').startsWith('api/media?path='),
  rejectedCount:rejected.length,
}}));
"""
    payload = _run_node(script)
    assert payload["transport"] == prompt
    assert payload["malformed"] == "hello\nworld"
    assert payload["literal"] == "json:[1,2,3]"
    assert payload["native"] == "native prompt"
    assert payload["transportMediaCount"] == 1
    assert payload["nativeMediaCount"] == 1
    assert payload["recoveredCount"] == 1
    assert payload["recoveredName"] == "screenshot.png"
    assert payload["recoveredUsesMediaEndpoint"] is True
    assert payload["rejectedCount"] == 0
    assert "SECRET_PIXELS" not in json.dumps(payload)


def test_projection_hides_only_the_adjacent_multimodal_shadow_duplicate():
    prompt = "[Workspace::v1: /tmp]\nInspect this screenshot.\n\n[Attached files: /tmp/screenshot.png]"
    transport = "\x00json:" + json.dumps(
        [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,SECRET_PIXELS"}},
        ]
    )
    helpers = "\n".join(
        [
            _between(UI_JS, "function _structuredMessageContentText", "function _serializedStructuredMessageContent"),
            _between(UI_JS, "function _serializedStructuredMessageContent", "function _isSerializedMultimodalShadow"),
            _between(UI_JS, "function _isSerializedMultimodalShadow", "function msgContent"),
            _between(UI_JS, "function msgContent", "function _isRecoveryControlMessageText"),
        ]
    )
    script = f"""
const fs=require('fs');const vm=require('vm');global.window=global;
{helpers}
global._messageIsRenderable=m=>!!(m&&m.role!=='tool'&&(msgContent(m)||(m.attachments||[]).length));
global._isContextCompactionMessage=()=>false;
global._isPreservedCompressionTaskListMessage=()=>false;
global._isRecoveryControlMessage=()=>false;
vm.runInThisContext(fs.readFileSync({json.dumps(str(PROJECTION_JS))},'utf8'));
const prompt={json.dumps(prompt)};
const transport={json.dumps(transport)};
const messages=[
  {{role:'user',content:prompt,attachments:[{{name:'screenshot.png'}}],timestamp:100}},
  {{role:'user',content:transport,timestamp:101}},
  {{role:'assistant',content:'Done.',timestamp:102,finish_reason:'stop'}},
];
const projected=HermesMessageProjection.project(messages);
const visible=projected.filter(entry=>entry.visible);
const latest=HermesMessageProjection.latestHumanPrompt(messages);
const distant=[
  messages[0],
  {{role:'user',content:transport,timestamp:120}},
];
process.stdout.write(JSON.stringify({{
  visible:visible.map(entry=>[entry.rawIdx,entry.semanticType,entry.turnId]),
  shadow:projected[1],
  latest:[latest.rawIdx,latest.turnId],
  distantVisible:HermesMessageProjection.visible(distant).map(entry=>entry.rawIdx),
}}));
"""
    payload = _run_node(script)
    assert payload["visible"] == [[0, "human_prompt", 1], [2, "assistant_final", 1]]
    assert payload["shadow"]["visible"] is False
    assert payload["shadow"]["boundary"] is False
    assert payload["latest"] == [0, 1]
    # Same content much later can be a deliberate repeat and must remain visible.
    assert payload["distantVisible"] == [0, 1]


def test_render_loop_uses_structured_text_and_media_instead_of_transport_bytes():
    render = UI_JS[UI_JS.index("function renderMessages"):]
    assert "const structured=_serializedStructuredMessageContent(content);" in render
    assert "content=structured.text;" in render
    assert "structuredMedia=structured.media||[];" in render
    assert "_serializedAttachmentMedia(content,structuredMedia.length)" in render
    assert "else if(structuredMedia.length)" in render
    assert "api/media?path=" in UI_JS
    assert "_renderAttachmentHtml(fname,String(item&&item.url||''))" in render
