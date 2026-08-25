from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
SESSIONS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
SW = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")


def _folder_render_block():
    start = SESSIONS.index("// Project chips")
    end = SESSIONS.index("const addChip=document.createElement", start)
    return SESSIONS[start:end]


def test_real_folder_pills_use_the_folder_color_as_the_surface_without_a_dot():
    block = _folder_render_block()
    assert "_applyProjectPillColor(chip,p.color);" in block
    assert "dot=document.createElement('span')" not in block
    assert "dot.className='color-dot'" not in block
    assert ".project-chip .color-dot" not in CSS
    assert ".project-chip.project-chip-colored{" in CSS
    assert "background:var(--project-color)" in CSS
    assert "color:var(--project-ink)" in CSS


def test_folder_pill_color_helper_normalizes_hex_and_selects_contrast_safe_ink():
    assert "function _normalizeProjectPillColor(value)" in SESSIONS
    assert "^#[0-9a-f]{3,4}$" in SESSIONS
    assert "^#[0-9a-f]{6}([0-9a-f]{2})?$" in SESSIONS
    assert "function _projectPillInk(hex)" in SESSIONS
    assert "const dark='#000000',light='#ffffff';" in SESSIONS
    assert "contrast(dark)>=contrast(light)?dark:light" in SESSIONS
    assert "chip.style.setProperty('--project-color',normalized);" in SESSIONS
    assert "chip.style.setProperty('--project-ink',_projectPillInk(normalized));" in SESSIONS


def test_colored_folder_pills_keep_distinct_interaction_states_on_desktop_and_mobile():
    assert ".project-chip.project-chip-colored:hover{" in CSS
    assert ".project-chip.project-chip-colored.active{" in CSS
    assert ".project-chip.project-chip-colored:focus-visible{" in CSS
    assert ".project-chip.project-chip-colored.long-pressing{" in CSS
    assert ".sidebar.mobile-session-page .project-chip.project-chip-colored{" in CSS
    assert ".sidebar.mobile-session-page .project-chip.project-chip-colored.active" in CSS
    assert ':root[data-skin="geist-contrast"] .project-chip.project-chip-colored' in CSS
    assert "@media(forced-colors:active)" in CSS


def test_neutral_filters_and_session_row_dots_are_unchanged():
    block = _folder_render_block()
    assert "_applyProjectPillColor(allChip" not in SESSIONS
    assert "_applyProjectPillColor(noneChip" not in SESSIONS
    assert "_applyProjectPillColor(addChip" not in SESSIONS
    assert "dot.className='session-project-dot';" in SESSIONS
    assert ".session-project-dot{" in CSS
    assert "dot.style.background=proj.color||'var(--blue)';" in SESSIONS
    assert "_applyProjectPillColor(chip,p.color);" in block


def test_folder_pill_color_assets_share_one_new_cache_identity():
    token = "&folder-pill-colors=v1"
    index_style = next(line for line in INDEX.splitlines() if "static/style.css?v=" in line)
    index_sessions = next(line for line in INDEX.splitlines() if "static/sessions.js?v=" in line)
    sw_style = next(line for line in SW.splitlines() if "'./static/style.css' + VQ" in line)
    sw_sessions = next(line for line in SW.splitlines() if "'./static/sessions.js' + VQ" in line)
    assert token in index_style and token in sw_style
    assert token in index_sessions and token in sw_sessions
