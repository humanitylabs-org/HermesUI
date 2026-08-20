"""Frontend-only warm transcript cache regression coverage."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SESSIONS_JS = (ROOT / "static" / "sessions.js").read_text()


def _cache_source() -> str:
    start = SESSIONS_JS.index("const _INITIAL_MSG_LIMIT = 30;")
    end = SESSIONS_JS.index(
        "// ============================================================================\n"
        "// COUPLED CONSTANT",
        start,
    )
    return SESSIONS_JS[start:end]


def _function_source(marker: str) -> str:
    start = SESSIONS_JS.index(marker)
    brace = SESSIONS_JS.index("{", start)
    depth = 0
    quote = None
    escaped = False
    for idx in range(brace, len(SESSIONS_JS)):
        char = SESSIONS_JS[idx]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return SESSIONS_JS[start : idx + 1]
    raise AssertionError(f"unbalanced JavaScript function: {marker}")


def test_session_switch_cache_is_frontend_only_and_integrated_before_clear():
    switch_start = SESSIONS_JS.index("async function loadSession(sid)")
    leave = SESSIONS_JS.index("if (currentSid && currentSid !== sid)", switch_start)
    cache = SESSIONS_JS.index("_cacheActiveSessionMessages(currentSid);", leave)
    clear = SESSIONS_JS.index("S.messages = [];", leave)
    assert cache < clear

    ensure_start = SESSIONS_JS.index("async function _ensureMessagesLoaded(sid")
    ensure_end = SESSIONS_JS.index("function _messageComparableText", ensure_start)
    ensure = SESSIONS_JS[ensure_start:ensure_end]
    assert "if(!opts.force&&typeof _takeFreshSessionMessageCache==='function')" in ensure
    assert "data=_takeFreshSessionMessageCache(sid,S.session);" in ensure
    assert ensure.index("if(!opts.force&&typeof _takeFreshSessionMessageCache==='function')") < ensure.index(
        "data=_takeFreshSessionMessageCache(sid,S.session);"
    )
    assert "_sessionMessagePrefetchInFlight.get(sid)" in ensure
    assert "if(!data){" in ensure
    assert "await api(" in ensure

    apply_start = SESSIONS_JS.index("function _applySessionListPayload(")
    apply_end = SESSIONS_JS.index("function _mergeRenderSessionListOptions", apply_start)
    assert "_scheduleSessionMessagePrefetch();" in SESSIONS_JS[apply_start:apply_end]

    load_end = SESSIONS_JS.index("// ── Handoff hint logic", switch_start)
    load_body = SESSIONS_JS[switch_start:load_end]
    force_call = "_ensureMessagesLoaded(sid, {force:forceReload, loadGeneration:_loadGeneration})"
    assert load_body.count(force_call) == 2
    assert "_ensureMessagesLoaded(sid, {force:_keepStaleUntilLoaded" not in load_body


def test_warm_cache_lru_freshness_clone_and_prefetch_deduplication():
    harness = f"""
const assert = require('assert');
let _allSessions = [];
const S = {{session:null,messages:[],toolCalls:[],busy:false,activeStreamId:null,activeProfile:'default'}};
let _messagesTruncated=false;
let _oldestIdx=0;
let _msgLimitMax=500;
const _MSG_LIMIT_MAX=500;
function _sessionSidebarSortCompare(a,b){{return Number(b.updated_at||0)-Number(a.updated_at||0);}}
function _isExternalSession(session){{return !!session.external;}}
function _profileMatchesActiveProfile(a,b){{return a===b;}}
let apiCalls=0;
let api=async url=>{{
  apiCalls++;
  const sid=new URL('https://local'+url).searchParams.get('session_id');
  await new Promise(resolve=>setTimeout(resolve,5));
  return {{session:{{session_id:sid,message_count:1,messages:[{{role:'user',content:sid}}]}}}};
}};
{_cache_source()}

assert.strictEqual(_storeSessionMessageCache('a', {{message_count:1,messages:[{{role:'user',content:'original'}}]}}), true);
const first=_takeFreshSessionMessageCache('a',{{message_count:1}});
assert.strictEqual(first.session.messages[0].content,'original');
first.session.messages[0].content='mutated';
assert.strictEqual(_takeFreshSessionMessageCache('a',{{message_count:1}}).session.messages[0].content,'original');
assert.strictEqual(_takeFreshSessionMessageCache('a',{{message_count:2}}),null);
assert.strictEqual(_sessionMessageCache.has('a'),false);
assert.strictEqual(_storeSessionMessageCache('streaming',{{message_count:1,active_stream_id:'run',messages:[]}}),false);

for(let i=0;i<6;i++) _storeSessionMessageCache('lru-'+i,{{message_count:1,messages:[{{role:'user',content:String(i)}}]}});
assert.strictEqual(_sessionMessageCache.size,5);
assert.strictEqual(_sessionMessageCache.has('lru-0'),false);

_sessionMessageCache.clear();
_allSessions=[
  // Sidebar counts are approximate and may differ from authoritative session
  // metadata. That must not trigger repeat prefetches; loadSession validates the
  // entry against fresh metadata before use.
  {{session_id:'prefetch',message_count:99,updated_at:10,profile:'default'}},
  {{session_id:'external',message_count:1,updated_at:9,profile:'default',external:true}},
  {{session_id:'other-profile',message_count:1,updated_at:8,profile:'work'}},
];
await Promise.all([
  _prefetchSessionMessages(_allSessions[0]),
  _prefetchSessionMessages(_allSessions[0]),
]);
assert.strictEqual(apiCalls,1);
assert.ok(_freshSessionMessageCacheEntry('prefetch',{{message_count:1}}));
await _prefetchSessionMessages(_allSessions[0]);
assert.strictEqual(apiCalls,1);
assert.strictEqual(_sessionMessagePrefetchEligible(_allSessions[1]),false);
assert.strictEqual(_sessionMessagePrefetchEligible(_allSessions[2]),false);
console.log(JSON.stringify({{ok:true,apiCalls,cacheSize:_sessionMessageCache.size}}));
"""
    result = subprocess.run(
        ["node", "--input-type=commonjs", "-e", f"(async()=>{{{harness}}})().catch(e=>{{console.error(e);process.exit(1)}});"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip()) == {"ok": True, "apiCalls": 1, "cacheSize": 1}


def test_force_refresh_bypasses_a_matching_warm_entry_behaviorally():
    start = SESSIONS_JS.index("async function _ensureMessagesLoaded(sid, opts)")
    end = SESSIONS_JS.index("function _messageComparableText", start)
    ensure = SESSIONS_JS[start:end]
    harness = f"""
const assert = require('assert');
const S = {{
  session:{{session_id:'forced',message_count:1,profile:'default'}},
  messages:[],toolCalls:[],lastUsage:{{}},activeProfile:'default',busy:false,activeStreamId:null,
}};
const window = {{}};
const INFLIGHT = {{}};
let _messagesTruncated=false;
let _oldestIdx=0;
let _msgLimitMax=500;
const _MSG_LIMIT_MAX=500;
let _pendingCarryForwardSnapshot=null;
let _loadingSessionId='forced';
let _loadSessionGeneration=1;
function _sessionSidebarSortCompare(){{return 0;}}
function _isSessionEffectivelyStreaming(){{return false;}}
function _isExternalSession(){{return false;}}
function _profileMatchesActiveProfile(a,b){{return a===b;}}
function _clearSameSessionForceReloadHint(){{}}
function _messageReloadLimitForSession(){{return 30;}}
function _syncToolCallsForLoadedMessages(){{}}
function clearLiveToolCards(){{}}
function clearVisibleMessageRowCache(){{}}
function _isSessionActivelyViewedForList(){{return false;}}
let apiCalls=0;
async function api(){{
  apiCalls++;
  return {{session:{{session_id:'forced',message_count:1,profile:'default',messages:[{{role:'assistant',content:'fresh'}}]}}}};
}}
{_cache_source()}
{ensure}
assert.strictEqual(_storeSessionMessageCache('forced',{{session_id:'forced',message_count:1,profile:'default',messages:[{{role:'assistant',content:'stale'}}]}}),true);
await _ensureMessagesLoaded('forced',{{force:true,loadGeneration:1}});
assert.strictEqual(apiCalls,1);
assert.strictEqual(S.messages[0].content,'fresh');
console.log(JSON.stringify({{ok:true,apiCalls,content:S.messages[0].content}}));
"""
    result = subprocess.run(
        ["node", "--input-type=commonjs", "-e", f"(async()=>{{{harness}}})().catch(e=>{{console.error(e);process.exit(1)}});"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip()) == {"ok": True, "apiCalls": 1, "content": "fresh"}


def test_prefetch_global_concurrency_stale_completion_and_execution_gates():
    harness = f"""
const assert = require('assert');
let _allSessions=[];
const S={{session:null,messages:[],toolCalls:[],busy:false,activeStreamId:null,activeProfile:'default'}};
let _messagesTruncated=false;
let _oldestIdx=0;
let _msgLimitMax=500;
const _MSG_LIMIT_MAX=500;
let hidden=false;
const document={{get hidden(){{return hidden;}}}};
const navigator={{connection:{{saveData:false}}}};
const idle=[];
function requestIdleCallback(fn){{idle.push(fn);return idle.length;}}
function _sessionSidebarSortCompare(a,b){{return Number(b.updated_at||0)-Number(a.updated_at||0);}}
function _isExternalSession(session){{return !!session.external;}}
function _profileMatchesActiveProfile(a,b){{return a===b;}}
function _isSessionEffectivelyStreaming(session){{return !!(session&&(session.active_stream_id||session.pending_user_message||session.has_pending_user_message||session.is_streaming||session.cron_running));}}
const pending=[];
let networkActive=0;
let networkMax=0;
let requestCount=0;
let api=async url=>{{
  requestCount++;
  networkActive++;
  networkMax=Math.max(networkMax,networkActive);
  const sid=new URL('https://local'+url).searchParams.get('session_id');
  return new Promise(resolve=>pending.push({{sid,done:false,resolve:()=>{{
    networkActive--;
    resolve({{session:{{session_id:sid,message_count:1,profile:S.activeProfile,messages:[{{role:'user',content:sid}}]}}}});
  }}}}));
}};
{_cache_source()}
const rows=prefix=>Array.from({{length:4}},(_,i)=>({{session_id:`${{prefix}}-${{i}}`,message_count:1,profile:'default',updated_at:10-i}}));
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
function releaseOne(){{const item=pending.find(entry=>!entry.done);assert.ok(item);item.done=true;item.resolve();}}

// Two overlapping authoritative generations must share one global cap.
_allSessions=rows('old');
_sessionMessagePrefetchGeneration=1;
_scheduleSessionMessagePrefetch();
idle.shift()();
await tick();
assert.strictEqual(requestCount,2);
_allSessions=rows('new');
_sessionMessagePrefetchGeneration=2;
_sessionMessagePrefetchQueue=[];
_scheduleSessionMessagePrefetch();
idle.shift()();
await tick();
assert.strictEqual(requestCount,2);
assert.strictEqual(networkMax,2);
while(_sessionMessagePrefetchActive||_sessionMessagePrefetchQueue.length){{
  const unresolved=pending.find(entry=>!entry.done);
  if(unresolved) releaseOne();
  await tick();
}}
assert.strictEqual(networkMax,2);
assert.strictEqual([..._sessionMessageCache.keys()].some(sid=>sid.startsWith('old-')),false);
assert.strictEqual([..._sessionMessageCache.keys()].filter(sid=>sid.startsWith('new-')).length,4);

// A count change without accepting another completion must reject the old result.
_sessionMessageCache.clear();
_allSessions=[{{session_id:'stale-count',message_count:1,profile:'default'}}];
_sessionMessagePrefetchGeneration=3;
const staleCount=_prefetchSessionMessages(_allSessions[0],{{generation:3}});
await tick();
_allSessions=[{{session_id:'stale-count',message_count:2,profile:'default'}}];
releaseOne();
await staleCount;
assert.strictEqual(_sessionMessageCache.has('stale-count'),false);

// Same-count rows with newer authority must not accept an older transcript.
_allSessions=[{{session_id:'stale-time',message_count:1,profile:'default',updated_at:1}}];
_sessionMessagePrefetchGeneration=31;
const staleTime=_prefetchSessionMessages(_allSessions[0],{{generation:31}});
await tick();
_allSessions=[{{session_id:'stale-time',message_count:1,profile:'default',updated_at:2}}];
releaseOne();
await staleTime;
assert.strictEqual(_sessionMessageCache.has('stale-time'),false);

// Removal/profile supersession and a stream beginning mid-request are rejected.
_allSessions=[{{session_id:'removed',message_count:1,profile:'default'}}];
_sessionMessagePrefetchGeneration=4;
const removed=_prefetchSessionMessages(_allSessions[0],{{generation:4}});
await tick();
_allSessions=[];
releaseOne();
await removed;
assert.strictEqual(_sessionMessageCache.has('removed'),false);

_allSessions=[{{session_id:'streamed',message_count:1,profile:'default'}}];
_sessionMessagePrefetchGeneration=5;
const streamed=_prefetchSessionMessages(_allSessions[0],{{generation:5}});
await tick();
_allSessions=[{{session_id:'streamed',message_count:1,profile:'default',active_stream_id:'run'}}];
releaseOne();
await streamed;
assert.strictEqual(_sessionMessageCache.has('streamed'),false);

_allSessions=[{{session_id:'profiled',message_count:1,profile:'default'}}];
S.activeProfile='default';
_sessionMessagePrefetchGeneration=6;
const profiled=_prefetchSessionMessages(_allSessions[0],{{generation:6}});
await tick();
S.activeProfile='work';
_allSessions=[{{session_id:'profiled',message_count:1,profile:'work'}}];
releaseOne();
await profiled;
assert.strictEqual(_sessionMessageCache.has('profiled'),false);

// Delayed idle work and queued follow-on jobs recheck visibility at execution.
S.activeProfile='default';
_allSessions=rows('hidden');
_sessionMessagePrefetchGeneration=7;
hidden=false;
_scheduleSessionMessagePrefetch();
const delayed=idle.shift();
const beforeDelayed=requestCount;
hidden=true;
delayed();
await tick();
assert.strictEqual(requestCount,beforeDelayed);

hidden=false;
_sessionMessagePrefetchGeneration=8;
_scheduleSessionMessagePrefetch();
idle.shift()();
await tick();
const beforeBackground=requestCount;
assert.strictEqual(_sessionMessagePrefetchActive,2);
hidden=true;
releaseOne();
releaseOne();
while(_sessionMessagePrefetchActive) await tick();
assert.strictEqual(requestCount,beforeBackground);
assert.strictEqual(_sessionMessagePrefetchQueue.length,0);

console.log(JSON.stringify({{ok:true,networkMax,requestCount}}));
"""
    result = subprocess.run(
        ["node", "--input-type=commonjs", "-e", f"(async()=>{{{harness}}})().catch(e=>{{console.error(e);process.exit(1)}});"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload["ok"] is True
    assert payload["networkMax"] == 2
