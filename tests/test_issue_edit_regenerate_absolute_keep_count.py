"""Regression: edit/regenerate use absolute keep_count (#2184 pattern)."""

import json
import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
UI_JS = (REPO / "static" / "ui.js").read_text(encoding="utf-8")
NODE = shutil.which("node")


def _function_body(src: str, name: str) -> str:
    needle_async = f"async function {name}"
    start = src.index(needle_async)
    brace = src.index("{", start)
    depth = 0
    for i in range(brace, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    raise AssertionError(f"function {name!r} body not found")


def test_submit_edit_uses_absolute_keep_count():
    body = _function_body(UI_JS, "submitEdit")
    assert re.search(r"absoluteKeepCount\s*=\s*_messageSessionIndexForRawIdx\(msgIdx\)", body)
    assert "Number.isInteger(absoluteKeepCount)" in body
    assert "keep_count: absoluteKeepCount" in body


def test_regenerate_uses_absolute_keep_count():
    body = _function_body(UI_JS, "regenerateResponse")
    assert re.search(r"absoluteKeepCount\s*=\s*_messageSessionIndexForRawIdx\(assistantIdx\)", body)
    assert "Number.isInteger(absoluteKeepCount)" in body
    assert "keep_count: absoluteKeepCount" in body


def test_submit_edit_captures_absolute_before_await():
    body = _function_body(UI_JS, "submitEdit")
    cap = re.search(r"absoluteKeepCount\s*=\s*_messageSessionIndexForRawIdx\(msgIdx\)", body)
    assert cap
    first_await = re.search(r"\bawait\s+_ensureAllMessagesLoaded\b", body)
    assert first_await and cap.start() < first_await.start()


def _run_regenerate_driver(setup: str) -> dict:
    assert NODE is not None
    helpers_start = UI_JS.index("function _messageSessionIndexBase")
    helpers_end = UI_JS.index("function _messageVirtualScrollTopForVisibleIdx", helpers_start)
    regenerate = _function_body(UI_JS, "regenerateResponse")
    script = f"""
global._oldestIdx=0;
global._messagesTruncated=true;
global.msgContent=message=>String(message&&message.content||'');
global.renderMessages=()=>{{}};
global.setStatus=()=>{{}};
global.t=value=>value;
const composer={{value:''}};
global.$=()=>composer;
const apiCalls=[];
let sendSnapshots=[];
global.api=async(path,options={{}})=>{{apiCalls.push({{path,body:options.body?JSON.parse(options.body):null}});return {{}};}};
global.send=async()=>{{sendSnapshots.push(S.messages.map(message=>String(message&&message.content||'')));}};
{UI_JS[helpers_start:helpers_end]}
{regenerate}
(async()=>{{
{setup}
process.stdout.write(JSON.stringify({{apiCalls,sendSnapshots,composer:composer.value}}));
}})().catch(error=>{{console.error(error);process.exit(1);}});
"""
    result = subprocess.run(
        [NODE, "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(result.stdout)


def test_regenerate_loads_sparse_source_zero_projection_before_local_slice():
    payload = _run_regenerate_driver(
        """
global.S={session:{session_id:'sparse',message_revision:'rev-sparse'},busy:false,messages:[
  {role:'user',content:'Ship it',_display_source_index:0},
  {role:'assistant',content:'',_latest_turn_gap:{start_index:1,end_index:1800}},
  {role:'assistant',content:'Old final',_display_source_index:1800},
]};
global._ensureAllMessagesLoaded=async()=>{
  S.messages=Array.from({length:1802},(_,index)=>({
    role:index===0?'user':'assistant',
    content:index===0?'Ship it':(index===1800?'Old final':''),
  }));
  _messagesTruncated=false;
};
await regenerateResponse({closest:()=>({dataset:{msgIdx:'2'}})});
"""
    )
    assert payload["apiCalls"] == [
        {
            "path": "/api/session/truncate",
            "body": {
                "session_id": "sparse",
                "keep_count": 1800,
                "expected_message_count": 1802,
                "expected_message_revision": "rev-sparse",
            },
        }
    ]
    assert len(payload["sendSnapshots"]) == 1
    assert len(payload["sendSnapshots"][0]) == 1800
    assert "Old final" not in payload["sendSnapshots"][0]


def test_regenerate_skips_empty_hidden_semantic_control_when_finding_prompt():
    payload = _run_regenerate_driver(
        """
global.S={session:{session_id:'linked',message_revision:'rev-linked'},busy:false,messages:[
  {role:'user',content:'Run validation',_display_source_index:0},
  {role:'assistant',content:'Validation is still running',_display_source_index:1},
  {role:'user',content:'',_display_semantic_control:true,_source:'process_wakeup',_display_source_index:2},
  {role:'assistant',content:'Validation passed',_display_source_index:3},
]};
global._ensureAllMessagesLoaded=async()=>{_messagesTruncated=false;};
await regenerateResponse({closest:()=>({dataset:{msgIdx:'3'}})});
"""
    )
    assert payload["apiCalls"] == [
        {
            "path": "/api/session/truncate",
            "body": {
                "session_id": "linked",
                "keep_count": 3,
                "expected_message_count": 4,
                "expected_message_revision": "rev-linked",
            },
        }
    ]
    assert payload["composer"] == "Run validation"
    assert len(payload["sendSnapshots"]) == 1


def test_regenerate_fails_closed_if_sparse_projection_cannot_fully_load():
    payload = _run_regenerate_driver(
        """
global.S={session:{session_id:'sparse-failure',message_revision:'rev-sparse-failure'},busy:false,messages:[
  {role:'user',content:'Ship it',_display_source_index:0},
  {role:'assistant',content:'',_latest_turn_gap:{start_index:1,end_index:1800}},
  {role:'assistant',content:'Old final',_display_source_index:1800},
]};
global._ensureAllMessagesLoaded=async()=>{};
await regenerateResponse({closest:()=>({dataset:{msgIdx:'2'}})});
"""
    )
    assert payload["apiCalls"] == []
    assert payload["sendSnapshots"] == []


def test_regenerate_aborts_if_a_new_turn_starts_during_full_load():
    payload = _run_regenerate_driver(
        """
global.S={session:{session_id:'race',message_count:101,message_revision:'rev-race'},busy:false,messages:[
  {role:'user',content:'Original prompt',_display_source_index:0},
  {role:'assistant',content:'Old final',_display_source_index:100},
]};
global._ensureAllMessagesLoaded=async()=>{
  S.messages=Array.from({length:102},(_,index)=>({
    role:index===101?'user':(index===0?'user':'assistant'),
    content:index===101?'New prompt':(index===0?'Original prompt':(index===100?'Old final':'')),
  }));
  _messagesTruncated=false;
  S.busy=true;
};
await regenerateResponse({closest:()=>({dataset:{msgIdx:'1'}})});
"""
    )
    assert payload["apiCalls"] == []
    assert payload["sendSnapshots"] == []


def test_regenerate_aborts_if_full_load_observes_same_count_replacement():
    payload = _run_regenerate_driver(
        """
global.S={session:{session_id:'aba-local',message_count:2,message_revision:'rev-old'},busy:false,messages:[
  {role:'user',content:'Original prompt',_display_source_index:0},
  {role:'assistant',content:'Old answer',_display_source_index:1},
]};
global._ensureAllMessagesLoaded=async()=>{
  S.messages=[
    {role:'user',content:'Original prompt'},
    {role:'assistant',content:'New answer'},
  ];
  S.session.message_revision='rev-new';
  _messagesTruncated=false;
};
await regenerateResponse({closest:()=>({dataset:{msgIdx:'1'}})});
"""
    )
    assert payload["apiCalls"] == []
    assert payload["sendSnapshots"] == []


def test_regenerate_does_not_overwrite_local_successor_turn_after_truncate_await():
    payload = _run_regenerate_driver(
        """
global.S={session:{session_id:'post-truncate-race',message_count:2,message_revision:'rev-post'},busy:false,messages:[
  {role:'user',content:'Original prompt',_display_source_index:0},
  {role:'assistant',content:'Old final',_display_source_index:1},
]};
global._ensureAllMessagesLoaded=async()=>{_messagesTruncated=false;};
global.api=async(path,options={})=>{
  apiCalls.push({path,body:options.body?JSON.parse(options.body):null});
  S.messages.push({role:'user',content:'New prompt'});
  S.busy=true;
  return {};
};
await regenerateResponse({closest:()=>({dataset:{msgIdx:'1'}})});
"""
    )
    assert payload["apiCalls"] == [
        {
            "path": "/api/session/truncate",
            "body": {
                "session_id": "post-truncate-race",
                "keep_count": 1,
                "expected_message_count": 2,
                "expected_message_revision": "rev-post",
            },
        }
    ]
    assert payload["sendSnapshots"] == []


def test_truncate_endpoint_rejects_active_session(monkeypatch, tmp_path):
    from io import BytesIO
    from types import SimpleNamespace

    import api.models as models
    import api.routes as routes
    from api.models import Session

    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True)
    monkeypatch.setattr(models, "SESSION_DIR", session_dir)
    monkeypatch.setattr(models, "SESSION_INDEX_FILE", session_dir / "_index.json")
    models.SESSIONS.clear()
    session = Session(
        session_id="truncate-active-race",
        messages=[{"role": "user", "content": "New prompt"}],
    )
    session.active_stream_id = "active-stream"
    session.save()

    body = json.dumps(
        {
            "session_id": session.session_id,
            "keep_count": 0,
            "expected_message_count": 1,
            "expected_message_revision": routes._session_message_mutation_revision(session),
        }
    ).encode()
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    captured = {}

    def fake_bad(_handler, message, status=400):
        captured.update(payload={"error": message}, status=status)

    monkeypatch.setattr(routes, "bad", fake_bad)
    handler = SimpleNamespace(
        headers={"Content-Length": str(len(body))},
        rfile=BytesIO(body),
    )
    routes.handle_post(handler, SimpleNamespace(path="/api/session/truncate"))

    assert captured["status"] == 409
    loaded = Session.load(session.session_id)
    assert loaded is not None
    assert [message["content"] for message in loaded.messages] == ["New prompt"]


def test_truncate_endpoint_rejects_completed_history_count_conflict(monkeypatch, tmp_path):
    from io import BytesIO
    from types import SimpleNamespace

    import api.models as models
    import api.routes as routes
    from api.models import Session

    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True)
    monkeypatch.setattr(models, "SESSION_DIR", session_dir)
    monkeypatch.setattr(models, "SESSION_INDEX_FILE", session_dir / "_index.json")
    models.SESSIONS.clear()
    session = Session(
        session_id="truncate-count-race",
        messages=[
            {"role": "user", "content": "Old prompt"},
            {"role": "assistant", "content": "Old answer"},
            {"role": "user", "content": "New prompt"},
            {"role": "assistant", "content": "New answer"},
        ],
    )
    session.save()

    body = json.dumps(
        {
            "session_id": session.session_id,
            "keep_count": 1,
            "expected_message_count": 2,
            "expected_message_revision": routes._session_message_mutation_revision(session),
        }
    ).encode()
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    captured = {}

    def fake_bad(_handler, message, status=400):
        captured.update(payload={"error": message}, status=status)

    monkeypatch.setattr(routes, "bad", fake_bad)
    handler = SimpleNamespace(
        headers={"Content-Length": str(len(body))},
        rfile=BytesIO(body),
    )
    routes.handle_post(handler, SimpleNamespace(path="/api/session/truncate"))

    assert captured["status"] == 409
    loaded = Session.load(session.session_id)
    assert loaded is not None
    assert [message["content"] for message in loaded.messages] == [
        "Old prompt",
        "Old answer",
        "New prompt",
        "New answer",
    ]


def test_truncate_endpoint_rejects_same_count_replacement_revision_conflict(monkeypatch, tmp_path):
    from io import BytesIO
    from types import SimpleNamespace

    import api.models as models
    import api.routes as routes
    from api.models import Session

    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True)
    monkeypatch.setattr(models, "SESSION_DIR", session_dir)
    monkeypatch.setattr(models, "SESSION_INDEX_FILE", session_dir / "_index.json")
    models.SESSIONS.clear()
    session = Session(
        session_id="truncate-revision-aba",
        messages=[
            {"role": "user", "content": "Original prompt"},
            {"role": "assistant", "content": "Old answer"},
        ],
    )
    session.save()
    stale_revision = routes._session_message_mutation_revision(session)

    session.messages[1] = {"role": "assistant", "content": "New answer"}
    session.save()
    assert routes._session_message_mutation_revision(session) != stale_revision

    body = json.dumps(
        {
            "session_id": session.session_id,
            "keep_count": 1,
            "expected_message_count": 2,
            "expected_message_revision": stale_revision,
        }
    ).encode()
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    captured = {}

    def fake_bad(_handler, message, status=400):
        captured.update(payload={"error": message}, status=status)

    monkeypatch.setattr(routes, "bad", fake_bad)
    handler = SimpleNamespace(
        headers={"Content-Length": str(len(body))},
        rfile=BytesIO(body),
    )
    routes.handle_post(handler, SimpleNamespace(path="/api/session/truncate"))

    assert captured["status"] == 409
    loaded = Session.load(session.session_id)
    assert loaded is not None
    assert [message["content"] for message in loaded.messages] == [
        "Original prompt",
        "New answer",
    ]


def test_truncate_endpoint_accepts_matching_idle_history_count(monkeypatch, tmp_path):
    from io import BytesIO
    from types import SimpleNamespace

    import api.models as models
    import api.routes as routes
    from api.models import Session

    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True)
    monkeypatch.setattr(models, "SESSION_DIR", session_dir)
    monkeypatch.setattr(models, "SESSION_INDEX_FILE", session_dir / "_index.json")
    models.SESSIONS.clear()
    session = Session(
        session_id="truncate-matching-count",
        messages=[
            {"role": "user", "content": "Old prompt"},
            {"role": "assistant", "content": "Old answer"},
            {"role": "user", "content": "Discard me"},
        ],
    )
    session.save()

    body = json.dumps(
        {
            "session_id": session.session_id,
            "keep_count": 2,
            "expected_message_count": 3,
            "expected_message_revision": routes._session_message_mutation_revision(session),
        }
    ).encode()
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)
    captured = {}

    def fake_j(_handler, payload, status=200, extra_headers=None):
        captured.update(payload=payload, status=status)

    monkeypatch.setattr(routes, "j", fake_j)
    handler = SimpleNamespace(
        headers={"Content-Length": str(len(body))},
        rfile=BytesIO(body),
    )
    routes.handle_post(handler, SimpleNamespace(path="/api/session/truncate"))

    assert captured["status"] == 200
    loaded = Session.load(session.session_id)
    assert loaded is not None
    assert [message["content"] for message in loaded.messages] == ["Old prompt", "Old answer"]
    response_revision = captured["payload"]["session"]["message_revision"]
    assert response_revision == routes._session_message_mutation_revision(loaded)
    assert len(response_revision) == 64
