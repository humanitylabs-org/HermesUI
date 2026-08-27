"""Regression coverage for compact raw-audio voice notes in chat."""

from pathlib import Path
import json
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
UI_PATH = ROOT / "static" / "ui.js"
STYLE_PATH = ROOT / "static" / "style.css"
INDEX_PATH = ROOT / "static" / "index.html"
SW_PATH = ROOT / "static" / "sw.js"
UI = UI_PATH.read_text(encoding="utf-8")
STYLE = STYLE_PATH.read_text(encoding="utf-8")
INDEX = INDEX_PATH.read_text(encoding="utf-8")
SW = SW_PATH.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    marker = f"function {name}"
    start = UI.index(marker)
    brace = UI.index("{", start)
    depth = 0
    quote = None
    escaped = False
    template_expr_depth = 0
    for idx in range(brace, len(UI)):
        char = UI[idx]
        if quote:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if quote == "`" and char == "$" and idx + 1 < len(UI) and UI[idx + 1] == "{":
                template_expr_depth += 1
                continue
            if char == quote and template_expr_depth == 0:
                quote = None
                continue
            if quote == "`" and char == "}" and template_expr_depth:
                template_expr_depth -= 1
            continue
        if char in ("'", '"', "`"):
            quote = char
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return UI[start : idx + 1]
    raise AssertionError(f"Could not extract {name}")


def _run_node(script: str):
    node = shutil.which("node")
    assert node, "node is required for the voice-note rendering regression"
    result = subprocess.run([node, "-e", script], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_microphone_webm_is_audio_but_generic_webm_stays_video():
    script = "\n".join(
        [
            "const _VIDEO_EXTS=/\\.(mp4|webm|mov|mkv|avi|m4v)(?:$|[?#])/i;",
            "const _AUDIO_EXTS=/\\.(mp3|wav|ogg|oga|m4a|aac|flac|opus|webm)(?:$|[?#])/i;",
            "const _IMAGE_EXTS=/\\.(png|jpe?g|gif|webp|avif)(?:$|[?#])/i;",
            _function_source("_isVoiceNoteName"),
            _function_source("_mediaKindForName"),
            "console.log(JSON.stringify({voice:_mediaKindForName('/x/voice-input-1787801774237.webm'),generic:_mediaKindForName('/x/demo.webm'),ogg:_mediaKindForName('voice-input-1.ogg')}));",
        ]
    )
    assert _run_node(script) == {"voice": "audio", "generic": "video", "ogg": "audio"}


def test_voice_note_player_is_compact_audio_without_file_editor_chrome():
    script = "\n".join(
        [
            "const MEDIA_PLAYBACK_RATES=[0.5,0.75,1,1.25,1.5,2];",
            "function esc(value){return String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\\"/g,'&quot;');}",
            "function _getStoredMediaPlaybackRate(){return 1;}",
            _function_source("_isVoiceNoteName"),
            _function_source("_mediaSpeedControlsHtml"),
            _function_source("_mediaPlayerHtml"),
            "const voice=_mediaPlayerHtml('audio','api/file/raw?x=1','voice-input-1787801774237.webm');",
            "const generic=_mediaPlayerHtml('audio','api/file/raw?x=2','interview.webm');",
            "console.log(JSON.stringify({voice,generic}));",
        ]
    )
    rendered = _run_node(script)
    assert 'class="msg-voice-note"' in rendered["voice"]
    assert "<audio" in rendered["voice"]
    assert "<video" not in rendered["voice"]
    assert "media-speed-controls" not in rendered["voice"]
    assert "msg-media-name" not in rendered["voice"]
    assert "msg-media-editor" in rendered["generic"]
    assert "media-speed-controls" in rendered["generic"]


def test_generated_upload_copy_is_hidden_only_when_attachments_match():
    script = "\n".join(
        [
            _function_source("_stripGeneratedUploadCopyForDisplay"),
            "const one=['voice-input-1787801774237.webm'];",
            "const two=['IMG_4938.png','voice-input-1787801774237.webm'];",
            "console.log(JSON.stringify({",
            " optimistic:_stripGeneratedUploadCopyForDisplay('Uploaded: voice-input-1787801774237.webm',one),",
            " persisted:_stripGeneratedUploadCopyForDisplay(\"I've uploaded 1 file(s): /tmp/voice-input-1787801774237.webm\",one),",
            " two:_stripGeneratedUploadCopyForDisplay(\"I've uploaded 2 file(s): /tmp/IMG_4938.png, /tmp/voice-input-1787801774237.webm\",two),",
            " caption:_stripGeneratedUploadCopyForDisplay('Please inspect this recording',one),",
            " mismatch:_stripGeneratedUploadCopyForDisplay('Uploaded: another.webm',one)",
            "}));",
        ]
    )
    assert _run_node(script) == {
        "optimistic": "",
        "persisted": "",
        "two": "",
        "caption": "Please inspect this recording",
        "mismatch": "Uploaded: another.webm",
    }


def test_voice_note_css_is_compact_and_empty_upload_bubble_is_removed():
    assert ".msg-voice-note{" in STYLE
    assert ".msg-voice-note-audio" in STYLE
    assert '.msg-row[data-role="user"] .msg-body:empty{display:none;}' in STYLE


def test_voice_note_asset_markers_bypass_same_version_pwa_cache():
    for source in (INDEX, SW):
        assert "voice-notes=v1" in source
    assert INDEX.count("voice-notes=v1") >= 2
    assert SW.count("voice-notes=v1") >= 2
