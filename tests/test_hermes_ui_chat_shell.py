from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_workspace_panel_is_absent_from_the_simplified_shell():
    assert "html body .rightpanel," in CSS
    assert "html body .workspace-panel-edge-toggle," in CSS
    assert "html body .composer-workspace-files-btn," in CSS
    assert "html body .workspace-toggle-btn," in CSS
    assert "html body .mobile-files-btn{display:none!important;}" in CSS


def test_workspace_selector_remains_usable_without_panel_button():
    assert ".composer-workspace-chip{border-left:0!important;border-radius:999px!important;padding-left:12px!important;}" in CSS
    assert ".composer-footer.cf-burger .composer-workspace-group{display:none!important;}" in CSS