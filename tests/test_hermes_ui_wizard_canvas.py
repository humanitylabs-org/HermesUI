from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
RAIL = (ROOT / "static" / "tailnet-app-rail.js").read_text(encoding="utf-8")
SW = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
SOURCE = (ROOT / "hermesui" / "wizard-canvas" / "src" / "main.jsx").read_text(encoding="utf-8")
SOURCE_CSS = (ROOT / "hermesui" / "wizard-canvas" / "src" / "style.css").read_text(encoding="utf-8")
BUILD = ROOT / "static" / "wizard-canvas"


def test_wizard_icon_opens_one_embedded_desktop_canvas():
    assert 'id="tailnetWizardHome" aria-label="Wizard Canvas"' in INDEX
    assert 'id="wizardCanvasFrame" title="Wizard Canvas"' in INDEX
    assert 'static/wizard-canvas/index.html?overlay=wizard-canvas-v5' in INDEX
    assert "showWizardHome=isWizardHomeDesktop()" in RAIL
    assert "wizardHome.hidden=!showWizardHome" in RAIL
    assert "if(wizardHome)wizardHome.hidden=true" in RAIL
    assert 'html[data-tailnet-view="wizard-home"] .tailnet-app-workspace{display:none!important;}' in CSS


def test_canvas_is_self_hosted_and_cloud_actions_are_disabled():
    assert (BUILD / "index.html").is_file()
    assert (BUILD / "assets" / "app-v5.min.js").is_file()
    assert (BUILD / "EXCALIDRAW_LICENSE.txt").is_file()
    assert (BUILD / "fonts").is_dir()
    assert "@excalidraw/excalidraw" in SOURCE
    assert "https://excalidraw.com" not in SOURCE
    assert "loadScene: false" in SOURCE
    assert "saveToActiveFile: false" in SOURCE
    assert "export: false" in SOURCE
    assert "saveAsImage: false" in SOURCE


def test_canvas_has_a_transient_save_status_and_blank_only_watermark():
    assert "wizard-light-column.webp" not in SOURCE
    assert "wizard-canvas-watermark" in SOURCE
    assert "sceneReady && sceneBlank" in SOURCE
    assert "!elements.some(element => element && !element.isDeleted)" in SOURCE
    assert 'src="../wizard-hat-mark.svg"' in SOURCE
    assert "viewBackgroundColor: '#ffffff'" in SOURCE
    assert ".wizard-canvas-watermark" in SOURCE_CSS
    assert "height: 70%;" in SOURCE_CSS
    assert "place-items: center;" in SOURCE_CSS
    assert "Saving…" in SOURCE
    assert "'Saved'" in SOURCE
    assert "SAVED_VISIBLE_MS = 2600" in SOURCE
    assert "Saved on this server" not in SOURCE
    assert "renderTopRightUI={topRightUi}" in SOURCE


def test_canvas_uses_only_the_server_autosave_endpoint():
    assert "const ENDPOINT = '/apps/api/wizard-canvas';" in SOURCE
    assert "serializeAsJSON" in SOURCE
    assert "serializeAsJSON(elements, appState, files, 'local')" in SOURCE
    assert "baseRevision" in SOURCE
    assert "method: 'PUT'" in SOURCE
    assert "Changed in another tab" in SOURCE
    assert "wizard-canvas-v5" in SW
