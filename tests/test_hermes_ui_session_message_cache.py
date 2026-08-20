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


def test_session_switch_cache_is_frontend_only_and_integrated_before_clear():
    switch_start = SESSIONS_JS.index("async function loadSession(sid)")
    leave = SESSIONS_JS.index("if (currentSid && currentSid !== sid)", switch_start)
    cache = SESSIONS_JS.index("_cacheActiveSessionMessages(currentSid);", leave)
    clear = SESSIONS_JS.index("S.messages = [];", leave)
    assert cache < clear

    ensure_start = SESSIONS_JS.index("async function _ensureMessagesLoaded(sid")
    ensure_end = SESSIONS_JS.index("function _messageComparableText", ensure_start)
    ensure = SESSIONS_JS[ensure_start:ensure_end]
    assert "if(!opts.force)" in ensure
    assert "data=_takeFreshSessionMessageCache(sid,S.session);" in ensure
    assert ensure.index("if(!opts.force)") < ensure.index(
        "data=_takeFreshSessionMessageCache(sid,S.session);"
    )
    assert "_sessionMessagePrefetchInFlight.get(sid)" in ensure
    assert "if(!data){" in ensure
    assert "await api(" in ensure

    apply_start = SESSIONS_JS.index("function _applySessionListPayload(")
    apply_end = SESSIONS_JS.index("function _mergeRenderSessionListOptions", apply_start)
    assert "_scheduleSessionMessagePrefetch();" in SESSIONS_JS[apply_start:apply_end]


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
