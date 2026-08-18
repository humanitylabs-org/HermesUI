from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_workspace_panel_is_absent_only_from_the_dashboard_shell():
    prefix = 'html[data-session-view="dashboard"] body '
    assert f"{prefix}.rightpanel," in CSS
    assert f"{prefix}.workspace-panel-edge-toggle," in CSS
    assert f"{prefix}.composer-workspace-files-btn," in CSS
    assert f"{prefix}.workspace-toggle-btn," in CSS
    assert f"{prefix}.mobile-files-btn{{display:none!important;}}" in CSS
    assert "html body .rightpanel," not in CSS


def test_classic_view_keeps_the_upstream_workspace_panel_available():
    assert 'html[data-session-view="classic"] body .rightpanel' not in CSS


def test_workspace_selector_remains_usable_without_panel_button():
    assert ".composer-workspace-chip{border-left:0!important;border-radius:999px!important;padding-left:12px!important;}" in CSS
    assert ".composer-footer.cf-burger .composer-workspace-group{display:none!important;}" in CSS