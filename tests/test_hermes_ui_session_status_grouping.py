"""HermesUI sidebar groups conversations by live work state."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SESSIONS_PATH = ROOT / "static" / "sessions.js"
SESSIONS = SESSIONS_PATH.read_text(encoding="utf-8")
STYLE = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
SW = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
NODE = shutil.which("node")


def test_sidebar_renders_only_working_and_done_status_groups():
    assert "const groups=_sessionStatusGroups(orderedSessions);" in SESSIONS
    assert "{label:'Working',status:'working',items:working}" in SESSIONS
    assert "{label:'Done',status:'done',items:done}" in SESSIONS
    assert "hermes-status-groups-collapsed" in SESSIONS
    assert "hermes-date-groups-collapsed" not in SESSIONS
    assert "const pinned=orderedSessions.filter" not in SESSIONS
    assert "session-status-group-indicator" in SESSIONS
    assert "g.status==='working'?'is-streaming':'is-unread'" in SESSIONS
    assert ".session-status-group-indicator{" in STYLE


def test_new_session_launcher_separates_working_from_done():
    assert "function _sessionNewSessionLauncher()" in SESSIONS
    assert "button.id='btnSessionListNewChat'" in SESSIONS
    assert "if(g.status==='done') appendNewSessionLauncher();" in SESSIONS
    assert "if(g.status==='working') appendNewSessionLauncher();" in SESSIONS
    assert "appendNewSessionLauncher();\n  if(virtualAnchorScrollTop" in SESSIONS
    assert ".session-new-session-button{width:100%;min-height:44px" in STYLE
    assert ".session-new-session-proxy[hidden]{display:none!important;}" in STYLE
    assert "ids.push('btnSessionListNewChat')" in SESSIONS
    assert "button.disabled=pending" in SESSIONS
    assert "createElementNS('http://www.w3.org/2000/svg','svg')" in SESSIONS
    assert "plusPath.setAttribute('d','M8 3.5v9M3.5 8h9')" in SESSIONS
    assert "font-family:inherit;font-size:13px;font-weight:inherit;line-height:inherit" in STYLE
    assert "stroke-linecap:round" in STYLE
    assert "background:var(--accent)" not in STYLE[STYLE.index('.session-new-session-plus{'):STYLE.index('.sidebar-search{')]


def test_status_group_assets_have_matching_cache_identity():
    css_suffix = "&private-app-rail=v1&new-session-divider=v2"
    js_suffix = "&tab-polish=v1&status-groups=v1&new-session-divider=v2"
    index_css = next(line for line in INDEX.splitlines() if "static/style.css?v=" in line)
    sw_css = next(line for line in SW.splitlines() if "'./static/style.css' + VQ" in line)
    assert css_suffix in index_css
    assert css_suffix in sw_css
    assert f"static/sessions.js?v=__WEBUI_VERSION__{js_suffix}" in INDEX
    assert f"'./static/sessions.js' + VQ + '{js_suffix}'" in SW


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
def test_status_groups_share_row_spinner_signal_and_preserve_chronology():
    assert NODE is not None
    driver = r"""
const fs=require('fs');
const src=fs.readFileSync(process.argv[1],'utf8');
function extractFunc(name){
  const start=src.indexOf('function '+name);
  if(start<0) throw new Error(name+' not found');
  const brace=src.indexOf('{',start);
  let depth=0;
  for(let i=brace;i<src.length;i++){
    if(src[i]==='{') depth++;
    else if(src[i]==='}'){
      depth--;
      if(depth===0) return src.slice(start,i+1);
    }
  }
  throw new Error(name+' body did not close');
}
function _isSessionEffectivelyStreaming(s){
  return Boolean(s&&(s.is_streaming||s.cron_running||s.pending_user_message));
}
function _sessionSortTimestampMs(s){ return Number(s.updated_at||0); }
eval(extractFunc('_sessionSidebarWorking'));
eval(extractFunc('_sessionRunningSortRank'));
eval(extractFunc('_sessionSidebarSortCompare'));
eval(extractFunc('_sessionStatusGroups'));
const rows=[
  {session_id:'done-new',updated_at:300,pinned:true},
  {session_id:'child-working',updated_at:200,_child_session_streaming:true},
  {session_id:'own-working',updated_at:400,is_streaming:true},
  {session_id:'done-old',updated_at:100},
];
const grouped=_sessionStatusGroups([...rows].sort(_sessionSidebarSortCompare));
rows[1]._child_session_streaming=false;
rows[2].is_streaming=false;
const afterCompletion=_sessionStatusGroups([...rows].sort(_sessionSidebarSortCompare));
console.log(JSON.stringify({
  grouped:grouped.map(group=>({label:group.label,status:group.status,ids:group.items.map(row=>row.session_id)})),
  afterCompletion:afterCompletion.map(group=>({label:group.label,ids:group.items.map(row=>row.session_id)})),
}));
"""
    result = subprocess.run(
        [NODE, "-e", driver, str(SESSIONS_PATH)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["grouped"] == [
        {"label": "Working", "status": "working", "ids": ["own-working", "child-working"]},
        {"label": "Done", "status": "done", "ids": ["done-new", "done-old"]},
    ]
    assert payload["afterCompletion"] == [
        {"label": "Done", "ids": ["own-working", "done-new", "child-working", "done-old"]}
    ]
