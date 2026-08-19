"""HermesUI's E-Ink default remains frontend-only and migration-safe."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOT = (ROOT / "static" / "boot.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CONFIG = (ROOT / "api" / "config.py").read_text(encoding="utf-8")


def test_eink_is_a_builtin_light_only_frontend_skin():
    assert "{name:'E-Ink', value:'e-ink', scheme:'light'" in BOOT
    assert "const scheme=skin&&(skin.scheme||skin._extScheme);" in BOOT
    assert ':root[data-skin="e-ink"]' in CSS
    assert '--bg:#ffffff' in CSS
    assert '--text:#000000' in CSS
    assert '--border:#000000' in CSS


def test_eink_default_does_not_expand_the_backend_skin_enum():
    assert '"e-ink"' not in CONFIG
    assert "frontend-only overlay" in BOOT
    assert "srvAppearance.skin==='default'" in BOOT


def test_first_paint_defaults_to_eink_and_has_one_time_default_migration():
    assert "migrationKey='hermesui-eink-default-v1'" in HTML
    assert "s==='default'" in HTML
    assert "s='e-ink'" in HTML
    assert "m?m[1]:'e-ink'" in HTML
    assert "skin==='e-ink'?'light':theme" in HTML
    assert "s==='e-ink'?'#ffffff'" in HTML
    assert "lsSkin!=='default'||hasHermesUiDefaultMigration" in BOOT


def test_non_default_local_skin_is_not_rewritten_by_migration():
    migration_guard = HTML.index("if(!localStorage.getItem(migrationKey)&&s==='default')")
    appearance_resolution = HTML.index("var m=legacy[t]", migration_guard)
    guarded_block = HTML[migration_guard:appearance_resolution]
    assert "s==='default'" in guarded_block
    assert "graphite" not in guarded_block
    assert "poseidon" not in guarded_block