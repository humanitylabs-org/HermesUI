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
    assert 'static/wizard-canvas/index.html?overlay=wizard-canvas-v8' in INDEX
    assert "showWizardHome=isWizardHomeDesktop()" in RAIL
    assert "wizardHome.hidden=!showWizardHome" in RAIL
    assert "if(wizardHome)wizardHome.hidden=true" in RAIL
    assert 'html[data-tailnet-view="wizard-home"] .tailnet-app-workspace{display:none!important;}' in CSS


def test_canvas_is_self_hosted_and_cloud_actions_are_disabled():
    assert (BUILD / "index.html").is_file()
    assert (BUILD / "assets" / "app-v8.min.js").is_file()
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
    assert "const LIGHT_BACKGROUND = '#ffffff';" in SOURCE
    assert ".wizard-canvas-watermark" in SOURCE_CSS
    assert "height: 70%;" in SOURCE_CSS
    assert "place-items: center;" in SOURCE_CSS
    assert "Saving…" in SOURCE
    assert "'Saved'" in SOURCE
    assert "SAVED_VISIBLE_MS = 2600" in SOURCE
    assert "Saved on this server" not in SOURCE
    assert "renderTopRightUI={topRightUi}" in SOURCE


def test_selected_text_controls_are_reduced_to_the_writing_essentials():
    assert ':has(input[name="font-size"])' in SOURCE_CSS
    assert ':has(input[data-testid="opacity"])' in SOURCE_CSS
    assert ':has(.zIndexButton)' in SOURCE_CSS
    assert 'button[aria-label="Duplicate"]' in SOURCE_CSS
    assert 'button[aria-label="Delete"]' in SOURCE_CSS
    assert 'button[aria-label="Add link"]' in SOURCE_CSS


def test_canvas_uses_only_the_server_autosave_endpoint():
    assert "const ENDPOINT = '/apps/api/wizard-canvas';" in SOURCE
    assert "serializeAsJSON" in SOURCE
    assert "serializeAsJSON(elements, persistentAppState, files, 'local')" in SOURCE
    assert "baseRevision" in SOURCE
    assert "method: 'PUT'" in SOURCE
    assert "Changed in another tab" in SOURCE
    assert "wizard-canvas-v8" in SW


def test_canvas_dark_mode_is_local_and_follows_the_parent_shell():
    assert "theme={canvasTheme}" in SOURCE
    assert "excalidrawAPI={captureExcalidrawApi}" in SOURCE
    assert "event.data.type !== 'hermesui:theme'" in SOURCE
    assert "event.origin !== location.origin" in SOURCE
    assert "theme: 'light'" in SOURCE
    assert "viewBackgroundColor: LIGHT_BACKGROUND" in SOURCE
    assert "so a light/dark toggle never creates a server save" in SOURCE
    assert ':root[data-canvas-theme="dark"]' in SOURCE_CSS
    assert ":root.dark[data-skin=\"e-ink\"]" in CSS


def test_canvas_fits_all_restored_content_once_without_persisting_the_viewport():
    assert "INITIAL_FIT_VIEWPORT_FACTOR = 0.72" in SOURCE
    assert "initialElementsRef.current = initialScene?.elements || []" in SOURCE
    assert "api.scrollToContent(liveElements" in SOURCE
    assert "fitToViewport: true" in SOURCE
    assert "viewportZoomFactor: INITIAL_FIT_VIEWPORT_FACTOR" in SOURCE
    assert "animate: false" in SOURCE
    assert "maxZoom: 1" in SOURCE
    assert "initialFitDoneRef.current = true" in SOURCE
    assert "new ResizeObserver(() => fitInitialScene())" in SOURCE
    assert "scrollX: 0" in SOURCE
    assert "scrollY: 0" in SOURCE
    assert "zoom: { value: 1 }" in SOURCE
    assert "Pan and zoom are local view state" in SOURCE
