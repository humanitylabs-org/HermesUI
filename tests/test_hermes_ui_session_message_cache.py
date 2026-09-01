"""Frontend-only bounded transcript cache regression coverage."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SESSIONS_JS = (ROOT / "static" / "sessions.js").read_text()
BOOT_JS = (ROOT / "static" / "boot.js").read_text()
DASHBOARD_JS = (ROOT / "static" / "session-dashboard.js").read_text()
WORKSPACE_JS = (ROOT / "static" / "workspace.js").read_text()
PANELS_JS = (ROOT / "static" / "panels.js").read_text()
UI_JS = (ROOT / "static" / "ui.js").read_text()


def _cache_source() -> str:
    start = SESSIONS_JS.index("const _INITIAL_MSG_LIMIT = 6;")
    end = SESSIONS_JS.index(
        "// ============================================================================\n"
        "// COUPLED CONSTANT",
        start,
    )
    return SESSIONS_JS[start:end]


def _function_source(source: str, marker: str) -> str:
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    quote = None
    escaped = False
    for idx in range(brace, len(source)):
        char = source[idx]
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
                return source[start : idx + 1]
    raise AssertionError(f"unbalanced JavaScript function: {marker}")


def _run_node(harness: str) -> dict:
    result = subprocess.run(
        ["node", "--input-type=commonjs", "-e", f"(async()=>{{{harness}}})().catch(e=>{{console.error(e);process.exit(1)}});"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip())


def test_navigation_uses_one_small_tail_and_prewarms_only_hot_sessions():
    assert "const _INITIAL_MSG_LIMIT = 6;" in SESSIONS_JS
    assert "const _OLDER_MSG_LIMIT = 30;" in SESSIONS_JS
    ensure_start = SESSIONS_JS.index("async function _ensureMessagesLoaded(sid, opts)")
    ensure_end = SESSIONS_JS.index("function _messageComparableText", ensure_start)
    ensure = SESSIONS_JS[ensure_start:ensure_end]
    assert "data=_takeFreshSessionMessageCache(sid,S.session);" in ensure
    assert "msg_limit=${boundedReloadLimit}" in ensure
    assert "async function _warmSessionMessageCacheRows(rows, expectedProfile, expectedEpoch)" in SESSIONS_JS
    assert "function _scheduleSessionMessageWarmup(rows)" in SESSIONS_JS
    assert "if(!session||session.archived) return false;" in SESSIONS_JS
    assert "_scheduleSessionMessageWarmup(_allSessions);" in SESSIONS_JS


def test_manual_history_keeps_thirty_row_pages():
    older = _function_source(SESSIONS_JS, "async function _loadOlderMessages()")
    assert "const _INITIAL_MSG_LIMIT = _OLDER_MSG_LIMIT;" in older
    assert "(S.messages || []).length + _INITIAL_MSG_LIMIT" in older
    assert "msg_limit=${_INITIAL_MSG_LIMIT}" in older


def test_metadata_overlaps_draft_save_and_boot_reuses_only_root_preflight():
    start = SESSIONS_JS.index("async function loadSession(sid)")
    end = SESSIONS_JS.index("// ── Handoff hint logic", start)
    switch = SESSIONS_JS[start:end]
    assert switch.index("const _metadataPromise=") < switch.index("await _saveComposerDraftNow")
    assert switch.index("await _saveComposerDraftNow") < switch.index("const metadataResult=await _metadataPromise;")
    assert "opts.bootRestoreMetadata===true" in switch
    assert "!currentSid&&!forceReload" in switch
    assert "String(opts.prefetchedSession.profile||'default')===String(S.activeProfile||'default')" in switch

    helper = _function_source(BOOT_JS, "async function _savedSessionSidebarOnlyState(sid)")
    assert "return {sidebarOnly:archived||running, archived, session};" in helper
    assert "bootRestoreMetadata:!!(!urlSession" in BOOT_JS
    assert "prefetchedSession:(!urlSession" in BOOT_JS
    assert "newerSessionOwnsBoot" in BOOT_JS


def test_private_cache_is_same_tab_only_and_purged_on_auth_loss():
    assert "sessionStorage.setItem(_SESSION_MESSAGE_CACHE_STORAGE_KEY" in SESSIONS_JS
    assert "localStorage.setItem(_SESSION_MESSAGE_CACHE_STORAGE_KEY" not in SESSIONS_JS
    assert "caches.open(" not in _cache_source()
    assert "function _clearSessionMessageCache()" in SESSIONS_JS
    assert "_clearSessionMessageCache" in WORKSPACE_JS
    assert "_clearSessionMessageCache" in PANELS_JS
    assert "_clearSessionMessageCache" in UI_JS


def test_high_signal_prompt_evidence_is_cached_in_the_same_tab_only():
    assert "hermesui.high-signal-prompt-cache.v1" in DASHBOARD_JS
    assert "sessionStorage.setItem(PROMPT_EVIDENCE_STORAGE_KEY" in DASHBOARD_JS
    assert "localStorage.setItem(PROMPT_EVIDENCE_STORAGE_KEY" not in DASHBOARD_JS
    assert "const persisted=persistedPromptEvidence(key,resultAnchor);" in DASHBOARD_JS
    assert "if(text) persistPromptEvidence(key,sid,profile,resultAnchor,text,cacheEpoch);" in DASHBOARD_JS
    assert "cacheEpoch===promptEvidenceCacheEpoch" in DASHBOARD_JS
    assert "promptEvidenceScopeKey(sid,profile)" in DASHBOARD_JS
    assert "window._clearSessionDashboardPrivateCache=clearSessionDashboardPrivateCache" in DASHBOARD_JS
    assert "window._clearSessionDashboardPrivateCache" in SESSIONS_JS


def test_cache_has_independent_storage_and_memory_byte_ceilings():
    harness = f"""
const assert=require('assert');
const backing=new Map();
const sessionStorage={{getItem:k=>backing.has(k)?backing.get(k):null,setItem:(k,v)=>backing.set(k,String(v)),removeItem:k=>backing.delete(k)}};
const localStorage={{getItem:()=>null,setItem:()=>{{throw new Error('localStorage forbidden')}},removeItem:()=>{{}}}};
const S={{activeProfile:'default',session:null,messages:[],toolCalls:[],busy:false,activeStreamId:null}};
let _messagesTruncated=false;
let _oldestIdx=0;
let _msgLimitMax=500;
const _MSG_LIMIT_MAX=500;
{_cache_source()}
const stable=(sid,revision,content='warm')=>({{session_id:sid,profile:'default',message_count:1,updated_at:revision,messages:[{{role:'assistant',content}}]}});
assert.strictEqual(_storeSessionMessageCache('large',stable('large',10,'x'.repeat(400000))),true);
assert.strictEqual(_sessionMessageCache.has('large'),true);
assert.strictEqual(backing.has(_SESSION_MESSAGE_CACHE_STORAGE_KEY),false);
assert.strictEqual(_storeSessionMessageCache('pathological',stable('pathological',10,'x'.repeat(1100000))),false);
assert.strictEqual(_sessionMessageCache.has('pathological'),false);
let restored=_takeFreshSessionMessageCache('large',{{session_id:'large',profile:'default',message_count:99,updated_at:10}});
assert.strictEqual(restored.session.messages[0].content.length,400000);
restored.session.messages[0].content='mutated';
assert.strictEqual(_takeFreshSessionMessageCache('large',{{session_id:'large',profile:'default',updated_at:10}}).session.messages[0].content.length,400000);
assert.strictEqual(_takeFreshSessionMessageCache('large',{{session_id:'large',profile:'default',updated_at:11}}),null);
assert.strictEqual(_storeSessionMessageCache('missing-revision',{{session_id:'missing-revision',profile:'default',message_count:1,messages:[]}}),false);
assert.strictEqual(_storeSessionMessageCache('wrong-key',stable('other',12)),false);
assert.strictEqual(_storeSessionMessageCache('busy',{{...stable('busy',12),active_stream_id:'run-a',is_streaming:true}}),true);
assert.strictEqual(
  _takeFreshSessionMessageCache('busy',{{...stable('busy',99),active_stream_id:'run-a',is_streaming:true}}).session.messages[0].content,
  'warm'
);
assert.strictEqual(
  _takeFreshSessionMessageCache('busy',{{...stable('busy',100),active_stream_id:'run-b',is_streaming:true}}),
  null
);
assert.strictEqual(_storeSessionMessageCache('archived',{{...stable('archived',12),archived:true}}),false);
assert.strictEqual(_storeSessionMessageCache('idle-pending',stable('idle-pending',12)),true);
assert.strictEqual(_takeFreshSessionMessageCache('idle-pending',{{...stable('idle-pending',12),has_pending_user_message:true}}),null);
assert.strictEqual(_storeSessionMessageCache('idle-archived',stable('idle-archived',12)),true);
assert.strictEqual(_takeFreshSessionMessageCache('idle-archived',{{...stable('idle-archived',12),archived:true}}),null);
for(let i=0;i<6;i++)assert.strictEqual(_storeSessionMessageCache('lru-'+i,stable('lru-'+i,20+i,String(i))),true);
assert.strictEqual(_sessionMessageCache.size,5);
assert.strictEqual(_sessionMessageCache.has('lru-0'),false);
_clearSessionMessageCache();
assert.strictEqual(_sessionMessageCache.size,0);
assert.strictEqual(backing.has(_SESSION_MESSAGE_CACHE_STORAGE_KEY),false);
console.log(JSON.stringify({{ok:true}}));
"""
    assert _run_node(harness) == {"ok": True}


def test_warmup_fetches_active_and_idle_rows_but_never_archived_rows():
    harness = f"""
const assert=require('assert');
const backing=new Map();
const sessionStorage={{getItem:k=>backing.get(k)||null,setItem:(k,v)=>backing.set(k,String(v)),removeItem:k=>backing.delete(k)}};
const localStorage={{getItem:()=>null,setItem:()=>{{throw new Error('localStorage forbidden')}},removeItem:()=>{{}}}};
const S={{activeProfile:'default',session:null,messages:[],toolCalls:[],busy:false,activeStreamId:null}};
const window={{}};
const navigator={{connection:{{saveData:false}}}};
let _messagesTruncated=false;let _oldestIdx=0;let _msgLimitMax=500;const _MSG_LIMIT_MAX=500;
const calls=[];
async function api(url){{
  calls.push(url);
  const sid=new URL('https://example.test'+url).searchParams.get('session_id');
  const active=sid==='active';
  return {{session:{{session_id:sid,profile:'default',message_count:1,updated_at:10,active_stream_id:active?'run-a':null,is_streaming:active,messages:[{{role:'assistant',content:sid}}]}}}};
}}
{_cache_source()}
await _warmSessionMessageCacheRows([
  {{session_id:'active',profile:'default',updated_at:11,active_stream_id:'run-a',is_streaming:true}},
  {{session_id:'idle',profile:'default',updated_at:10}},
  {{session_id:'cold',profile:'default',updated_at:10,archived:true}},
], 'default', _sessionMessageCacheEpoch);
assert.deepStrictEqual(calls.map(url=>new URL('https://example.test'+url).searchParams.get('session_id')),['active','idle']);
assert.strictEqual(_sessionMessageCache.has('active'),true);
assert.strictEqual(_sessionMessageCache.has('idle'),true);
assert.strictEqual(_sessionMessageCache.has('cold'),false);
console.log(JSON.stringify({{ok:true,calls:calls.length}}));
"""
    assert _run_node(harness) == {"ok": True, "calls": 2}


def test_corrupt_cross_session_storage_is_rejected():
    harness = f"""
const assert=require('assert');
const key='hermesui.session-message-cache.v1';
const now=Date.now();
const corrupt={{version:1,entries:[['key-a',{{storedAt:now,messageCount:1,revision:'10',profile:'default',data:{{session:{{session_id:'key-b',profile:'default',message_count:1,updated_at:10,messages:[{{role:'assistant',content:'private'}}]}}}}}}]]}};
const backing=new Map([[key,JSON.stringify(corrupt)]]);
const sessionStorage={{getItem:k=>backing.get(k)||null,setItem:(k,v)=>backing.set(k,String(v)),removeItem:k=>backing.delete(k)}};
const localStorage={{getItem:()=>null,setItem:()=>{{}},removeItem:()=>{{}}}};
const S={{activeProfile:'default',session:null,messages:[],toolCalls:[],busy:false,activeStreamId:null}};
let _messagesTruncated=false;let _oldestIdx=0;let _msgLimitMax=500;const _MSG_LIMIT_MAX=500;
{_cache_source()}
assert.strictEqual(_sessionMessageCache.size,0);
assert.strictEqual(backing.has(key),false);
console.log(JSON.stringify({{ok:true}}));
"""
    assert _run_node(harness) == {"ok": True}


def test_force_refresh_bypasses_a_matching_warm_entry():
    ensure_start = SESSIONS_JS.index("async function _ensureMessagesLoaded(sid, opts)")
    ensure_end = SESSIONS_JS.index("function _messageComparableText", ensure_start)
    ensure = SESSIONS_JS[ensure_start:ensure_end]
    harness = f"""
const assert=require('assert');
const sessionStorage={{getItem:()=>null,setItem:()=>{{}},removeItem:()=>{{}}}};
const localStorage={{getItem:()=>null,setItem:()=>{{}},removeItem:()=>{{}}}};
const S={{session:{{session_id:'forced',message_count:1,profile:'default',updated_at:10}},messages:[],toolCalls:[],lastUsage:{{}},activeProfile:'default',busy:false,activeStreamId:null}};
const window={{}};const INFLIGHT={{}};
let _messagesTruncated=false;let _oldestIdx=0;let _msgLimitMax=500;const _MSG_LIMIT_MAX=500;
let _pendingCarryForwardSnapshot=null;let _loadingSessionId='forced';let _loadSessionGeneration=1;
function _clearSameSessionForceReloadHint(){{}} function _messageReloadLimitForSession(){{return 6;}}
function _syncToolCallsForLoadedMessages(){{}} function clearLiveToolCards(){{}} function clearVisibleMessageRowCache(){{}}
function _isSessionActivelyViewedForList(){{return false;}}
let apiCalls=0;
async function api(){{apiCalls++;return {{session:{{session_id:'forced',message_count:1,message_revision:'stable-rev',profile:'default',updated_at:11,messages:[{{role:'assistant',content:'fresh'}}]}}}};}}
{_cache_source()}
{ensure}
assert.strictEqual(_storeSessionMessageCache('forced',{{session_id:'forced',message_count:1,profile:'default',updated_at:10,messages:[{{role:'assistant',content:'stale'}}]}}),true);
await _ensureMessagesLoaded('forced',{{force:true,loadGeneration:1}});
assert.strictEqual(apiCalls,1);assert.strictEqual(S.messages[0].content,'fresh');assert.strictEqual(S.session.message_revision,'stable-rev');
console.log(JSON.stringify({{ok:true,apiCalls}}));
"""
    assert _run_node(harness) == {"ok": True, "apiCalls": 1}


def test_transcript_cache_cannot_be_repopulated_by_a_request_after_purge():
    ensure_start = SESSIONS_JS.index("async function _ensureMessagesLoaded(sid, opts)")
    ensure_end = SESSIONS_JS.index("function _messageComparableText", ensure_start)
    ensure = SESSIONS_JS[ensure_start:ensure_end]
    harness = f"""
const assert=require('assert');
const backing=new Map();
const sessionStorage={{getItem:k=>backing.get(k)||null,setItem:(k,v)=>backing.set(k,String(v)),removeItem:k=>backing.delete(k)}};
const localStorage={{getItem:()=>null,setItem:()=>{{}},removeItem:()=>{{}}}};
const S={{session:{{session_id:'race',message_count:1,profile:'default',updated_at:10}},messages:[],toolCalls:[],lastUsage:{{}},activeProfile:'default',busy:false,activeStreamId:null}};
const window={{_clearSessionDashboardPrivateCache:()=>{{}}}};const INFLIGHT={{}};
let _messagesTruncated=false;let _oldestIdx=0;let _msgLimitMax=500;const _MSG_LIMIT_MAX=500;
let _pendingCarryForwardSnapshot=null;let _loadingSessionId='race';let _loadSessionGeneration=1;
function _clearSameSessionForceReloadHint(){{}} function _messageReloadLimitForSession(){{return 6;}}
function _syncToolCallsForLoadedMessages(){{}} function clearLiveToolCards(){{}} function clearVisibleMessageRowCache(){{}}
function _isSessionActivelyViewedForList(){{return false;}}
let resolveApi;
async function api(){{return new Promise(resolve=>{{resolveApi=resolve;}});}}
{_cache_source()}
{ensure}
backing.set(_SESSION_MESSAGE_CACHE_STORAGE_KEY,'private');
backing.set('hermesui.high-signal-prompt-cache.v1','private');
const pending=_ensureMessagesLoaded('race',{{loadGeneration:1}});
await Promise.resolve();
_clearSessionMessageCache();
resolveApi({{session:{{session_id:'race',message_count:1,profile:'default',updated_at:10,messages:[{{role:'assistant',content:'authorized-before-logout'}}]}}}});
await pending;
assert.strictEqual(_sessionMessageCache.size,0);
assert.strictEqual(backing.has(_SESSION_MESSAGE_CACHE_STORAGE_KEY),false);
assert.strictEqual(backing.has('hermesui.high-signal-prompt-cache.v1'),false);
assert.strictEqual(_storeSessionMessageCache('race',S.session),false);
console.log(JSON.stringify({{ok:true}}));
"""
    assert _run_node(harness) == {"ok": True}


def test_cache_ttl_is_immutable_and_expired_storage_is_pruned():
    harness = f"""
const assert=require('assert');
const backing=new Map();
const sessionStorage={{getItem:k=>backing.get(k)||null,setItem:(k,v)=>backing.set(k,String(v)),removeItem:k=>backing.delete(k)}};
const localStorage={{getItem:()=>null,setItem:()=>{{}},removeItem:()=>{{}}}};
const S={{activeProfile:'default',session:null,messages:[],toolCalls:[],busy:false,activeStreamId:null}};
const window={{}};let _messagesTruncated=false;let _oldestIdx=0;let _msgLimitMax=500;const _MSG_LIMIT_MAX=500;
let now=1000000;Date.now=()=>now;
{_cache_source()}
const session={{session_id:'ttl',profile:'default',message_count:1,updated_at:10,messages:[{{role:'assistant',content:'warm'}}]}};
assert.strictEqual(_storeSessionMessageCache('ttl',session),true);
const storedAt=_sessionMessageCache.get('ttl').storedAt;
now+=_SESSION_MESSAGE_CACHE_TTL_MS-1;
assert.ok(_takeFreshSessionMessageCache('ttl',session));
assert.strictEqual(_sessionMessageCache.get('ttl').storedAt,storedAt);
now+=2;
assert.strictEqual(_takeFreshSessionMessageCache('ttl',session),null);
assert.strictEqual(backing.has(_SESSION_MESSAGE_CACHE_STORAGE_KEY),false);
console.log(JSON.stringify({{ok:true}}));
"""
    assert _run_node(harness) == {"ok": True}


def test_boot_401_purges_private_caches_and_user_navigation_owns_restore():
    redirect = _function_source(BOOT_JS, "const _redirectBootModelDropdownIfUnauth=(res)=>")
    assert "_clearSessionMessageCache" in redirect
    assert "const newerSessionOwnsBoot=!urlSession&&Boolean(" in BOOT_JS
    assert "S.session||(typeof _loadingSessionId!=='undefined'&&_loadingSessionId)" in BOOT_JS


def test_high_signal_stays_visible_when_small_tail_contains_only_hidden_rows():
    assert "const hasSession=!!current.session;" in DASHBOARD_JS
    assert "const visible=!!(instruction&&instruction.empty&&hasOlder);" in DASHBOARD_JS
