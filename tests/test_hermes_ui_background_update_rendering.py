"""Regression coverage for process-wakeup transcript rendering.

A background-process wakeup is stored as a synthetic user turn
(`_source: "process_wakeup"`). The trigger itself stays out of the transcript.
Standalone follow-ups remain compact background updates, while a wakeup whose
task id was launched inside the latest human turn resumes that turn normally.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
UI_JS_PATH = ROOT / "static" / "ui.js"
STYLE_CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
I18N_JS = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node not on PATH")


_DRIVER = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
function extractFunc(name){
  const start = src.indexOf('function ' + name);
  if(start === -1) throw new Error(name + ' not found');
  const params = src.indexOf('(', start);
  let depth = 0, close = -1;
  for(let i=params; i<src.length; i++){
    if(src[i] === '(') depth++;
    else if(src[i] === ')'){
      depth--;
      if(depth === 0){ close = i; break; }
    }
  }
  const brace = src.indexOf('{', close);
  depth = 0;
  for(let i=brace; i<src.length; i++){
    if(src[i] === '{') depth++;
    else if(src[i] === '}'){
      depth--;
      if(depth === 0) return src.slice(start, i + 1);
    }
  }
  throw new Error(name + ' body did not close');
}
function msgContent(m){
  if(!m) return '';
  if(typeof m.content === 'string') return m.content;
  if(Array.isArray(m.content)) return m.content.map(p => (p && (p.text || p.content)) || '').join('\n');
  return String(m.content || '');
}
function _isContextCompactionMessage(){ return false; }
function _isPreservedCompressionTaskListMessage(){ return false; }
function _isRecoveryControlMessage(){ return false; }
function _messageHasReasoningPayload(){ return false; }
function _assistantMessageHasVisibleContent(m){ return !!String(msgContent(m)).trim(); }

global.window = {};
global.S = {messages: []};
let _visWithIdxCache = null;
let _visWithIdxCacheLen = 0;
let _visWithIdxCacheSrc = null;

const heightStart = src.indexOf('const MESSAGE_RENDER_WINDOW_DEFAULT');
const heightEnd = src.indexOf('const MESSAGE_VIRTUAL_MEASUREMENT_MAX_RERENDERS', heightStart);
if(heightStart !== -1 && heightEnd !== -1) eval(src.slice(heightStart, heightEnd));
eval(extractFunc('_backgroundUpdateControlText'));
eval(extractFunc('_isBackgroundUpdateTriggerMessage'));
eval(extractFunc('_assistantContinuesUserDirectedTurn'));
eval(extractFunc('_backgroundUpdateTaskId'));
eval(extractFunc('_backgroundUpdateResumesUserRun'));
eval(extractFunc('_stripWorkspaceDisplayPrefix'));
eval(extractFunc('_stripAttachedFilesMarkerForDisplay'));
eval(extractFunc('_messageIsRenderable'));
eval(extractFunc('_getVisibleMessagesWithIdx'));
eval(extractFunc('_messageVirtualRoleForEntry'));

const wakeup = {
  role: 'user',
  content: '[IMPORTANT: Background process proc_123 completed (exit_code=0).\nCommand: sleep 1\nOutput:\ndone]',
  _source: 'process_wakeup',
  timestamp: 1783405253.72,
};
S.messages = [
  {role: 'assistant', content: 'previous assistant report', timestamp: 1783405252.05},
  wakeup,
  {role: 'assistant', content: 'assistant response to wakeup', timestamp: 1783405254.10},
];

const visible = _getVisibleMessagesWithIdx();
const turns = [];
let current = [];
for(const entry of visible){
  const source = entry.m._source || '';
  if(entry.m.role === 'user'){
    if(current.length) turns.push(current);
    turns.push(['user:' + source + ':' + String(entry.m.content).slice(0, 35)]);
    current = [];
  }else if(entry.m.role === 'assistant'){
    current.push('assistant:' + entry.m.content);
  }
}
if(current.length) turns.push(current);
const virtualRole = _messageVirtualRoleForEntry(visible[1]);
const virtualHeight = typeof _messageVirtualDefaultHeightForRole === 'function'
  ? _messageVirtualDefaultHeightForRole(virtualRole)
  : null;
const attachmentOnlyWakeup = {
  role: 'user',
  content: '',
  _source: 'process_wakeup',
  attachments: [{name: 'result.txt'}],
};
const markerWakeupContent = [
  '[Workspace::v1: /tmp/hermes]',
  'Visible wakeup text',
  '',
  '[Attached files: result.txt]',
].join(String.fromCharCode(10));

_visWithIdxCache = null;
_visWithIdxCacheLen = 0;
_visWithIdxCacheSrc = null;
S.messages = [
  {role:'assistant',content:'Deploying now.',tool_calls:[{function:{name:'terminal'}}],finish_reason:'tool_calls'},
  {role:'user',content:'[Workspace::v1: /home/oscar/workspace]\n[ASYNC DELEGATION BATCH COMPLETE — deleg_6695d6f0]\nA background fan-out finished.'},
  {role:'assistant',content:'Live now and verified.',finish_reason:'stop'},
  {role:'user',content:'[IMPORTANT: Background process proc_9 completed (exit_code=0).]',_source:'process_wakeup'},
  {role:'assistant',content:'Independent review completed.',finish_reason:'stop'},
];
const interleaved = _getVisibleMessagesWithIdx().map(entry=>({
  text:String(entry.m.content||''),
  backgroundUpdate:!!entry.backgroundUpdate,
}));

_visWithIdxCache = null;
_visWithIdxCacheLen = 0;
_visWithIdxCacheSrc = null;
S.messages = [
  {role:'user',content:'Run the long verification.'},
  {role:'assistant',content:'',tool_calls:[{function:{name:'terminal'}}],finish_reason:'tool_calls'},
  {role:'tool',content:'Started background process proc_linked_1.'},
  {role:'assistant',content:'Verification is still running.',finish_reason:'stop'},
  {role:'user',content:'[IMPORTANT: Background process proc_linked_1 completed (exit_code=0).]',_source:'process_wakeup',_wakeup_meta:{task_id:'proc_linked_1'}},
  {role:'assistant',content:'Verification passed and the change is live.',finish_reason:'stop'},
];
const linked = _getVisibleMessagesWithIdx().map(entry=>({
  text:String(entry.m.content||''),
  backgroundUpdate:!!entry.backgroundUpdate,
}));

process.stdout.write(JSON.stringify({
  visible: visible.map(e => ({rawIdx: e.rawIdx, role: e.m.role, source: e.m._source || '', backgroundUpdate: !!e.backgroundUpdate, text: String(e.m.content).slice(0, 32)})),
  turns,
  virtualRole,
  virtualHeight,
  attachmentOnlyRenderable: _messageIsRenderable(attachmentOnlyWakeup),
  strippedWakeupDisplay: _stripAttachedFilesMarkerForDisplay(_stripWorkspaceDisplayPrefix(markerWakeupContent)),
  interleaved,
  linked,
}));
"""


def _run_driver():
    assert NODE is not None
    proc = subprocess.run(
        [NODE, "-e", _DRIVER, str(UI_JS_PATH)],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_process_wakeup_trigger_is_hidden_and_followup_is_intermediary():
    result = _run_driver()

    assert result["visible"] == [
        {"rawIdx": 0, "role": "assistant", "source": "", "backgroundUpdate": False, "text": "previous assistant report"},
        {"rawIdx": 2, "role": "assistant", "source": "", "backgroundUpdate": True, "text": "assistant response to wakeup"},
    ]


def test_background_update_has_a_compact_virtual_height_role():
    result = _run_driver()

    assert result["virtualRole"] == "process_wakeup"
    assert isinstance(result["virtualHeight"], int)
    assert 1 <= result["virtualHeight"] <= 120


def test_interleaved_wakeup_does_not_capture_the_real_user_run_result():
    result = _run_driver()
    assert result["interleaved"] == [
        {"text": "Deploying now.", "backgroundUpdate": False},
        {"text": "Live now and verified.", "backgroundUpdate": False},
        {"text": "Independent review completed.", "backgroundUpdate": True},
    ]


def test_linked_process_completion_keeps_direct_final_answer_out_of_background_updates():
    result = _run_driver()
    assert result["linked"][-2:] == [
        {"text": "Verification is still running.", "backgroundUpdate": False},
        {"text": "Verification passed and the change is live.", "backgroundUpdate": False},
    ]


def test_attachment_only_process_wakeup_is_hidden_and_display_helpers_still_work():
    result = _run_driver()

    assert result["attachmentOnlyRenderable"] is False
    assert result["strippedWakeupDisplay"] == "Visible wakeup text"


def test_process_wakeup_followup_uses_collapsed_background_update_not_normal_answer():
    ui = UI_JS_PATH.read_text(encoding="utf-8")
    marker = "const isBackgroundUpdate="
    marker_idx = ui.find(marker)
    assert marker_idx != -1, "render loop must classify background updates"
    process_branch_idx = ui.find("if(isBackgroundUpdate)", marker_idx)
    user_branch_idx = ui.find("if(isUser)", marker_idx)

    assert process_branch_idx != -1, "process-wakeup render branch missing"
    assert user_branch_idx != -1, "normal user render branch missing"
    assert process_branch_idx < user_branch_idx, (
        "background updates must render through the compact status branch "
        "before the normal user-bubble branch"
    )
    process_branch = ui[process_branch_idx:user_branch_idx]
    assert "background-update-row" in process_branch
    assert "background-update-card" in process_branch
    assert "dataset.role='background_updates'" in process_branch
    assert "dataset.role='background_update'" in process_branch
    assert "${filesHtml}" in process_branch
    assert "Later updates" in process_branch
    assert "background-update-count" in process_branch
    assert "background-update-item" in process_branch
    assert "transcript-disclosure-summary" in process_branch
    assert "tool-worklog-summary" in process_branch
    assert "transcript-disclosure-chevron" in process_branch
    assert "const disclosureOpen=_readActivityDisclosureState(disclosureKey)==='open';" in process_branch
    assert "${disclosureOpen?' open':''}" in process_branch
    assert "ontoggle=\"_onBackgroundUpdateToggle(this)\"" in process_branch
    assert "const rowDisplayContent=displayContent;" in ui
    assert "const rowDisplayContent=isProcessWakeup?content:displayContent;" not in ui

    assert ".background-update-row" in STYLE_CSS
    assert ".background-update-card" in STYLE_CSS
    notice_rule = STYLE_CSS[
        STYLE_CSS.index(".background-update-card{") : STYLE_CSS.index(".background-update-card>summary{")
    ]
    assert "margin:4px 0 14px" in notice_rule
    assert "max-width:var(--msg-max)" in notice_rule
    assert "border:0" in notice_rule
    assert ".background-update-card > .transcript-disclosure-summary" in STYLE_CSS


def test_blank_turn_failsafe_keeps_nonempty_work_details_collapsed():
    ui = UI_JS_PATH.read_text(encoding="utf-8")
    failsafe = ui.split("Fail-safe invariant (#3875)", 1)[1].split("// Re-attach the preserved live turn", 1)[0]
    assert "A non-empty Work details summary is itself visible and expandable" in failsafe
    assert "group.classList.remove('tool-call-group-collapsed')" not in failsafe
    assert "Normalize every settled Work" in failsafe
    assert "group.classList.add('open')" not in failsafe
    assert "removeAttribute('aria-hidden')" in failsafe, (
        "The last-resort source fallback must remain for truly empty groups"
    )


def test_process_wakeup_label_key_exists_in_all_locales():
    locale_pattern = re.compile(
        r"^\s{2}(?:'(?P<quoted>[A-Za-z0-9-]+)'|(?P<plain>[A-Za-z0-9-]+))\s*:\s*\{",
        re.MULTILINE,
    )
    locale_matches = list(locale_pattern.finditer(I18N_JS))
    assert locale_matches, "expected at least the English locale"
    for idx, match in enumerate(locale_matches):
        name = match.group("quoted") or match.group("plain")
        start = match.end()
        end = locale_matches[idx + 1].start() if idx + 1 < len(locale_matches) else I18N_JS.find("\n};", start)
        block = I18N_JS[start:end]
        assert re.search(r"\bprocess_wakeup_label\s*:", block), (
            f"process_wakeup_label missing from locale {name}"
        )
    assert "process_wakeup_label:'Background wakeup'" in I18N_JS
