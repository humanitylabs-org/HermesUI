import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "hermesui" / "run_upstream_compatibility.py"
MANIFEST_PATH = ROOT / "hermesui" / "upstream-frontend-replacements.json"
ISOLATED_MANIFEST_PATH = ROOT / "hermesui" / "upstream-isolated-tests.json"


def _runner_module():
    spec = importlib.util.spec_from_file_location("hermesui_compat", RUNNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_replacement_manifest_is_exact_pinned_and_has_real_downstream_coverage():
    module = _runner_module()
    replacements = module.load_replacements()
    upstream = json.loads((ROOT / "UPSTREAM.json").read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["upstream_commit"] == upstream["commit"]
    assert len(replacements) == 25
    nodeids = [entry["nodeid"] for entry in replacements]
    assert len(nodeids) == len(set(nodeids))
    assert all(nodeid.startswith("tests/test_") for nodeid in nodeids)
    assert all(
        replacement.startswith("tests/test_hermes")
        for entry in replacements
        for replacement in entry["covered_by"]
    )


def test_replacements_only_cover_frontend_contract_families():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    allowed_files = {
        "test_issue3227_help_tab.py",
        "test_issue4391_settings_shortcut.py",
        "test_issue4553_mobile_transcript_overflow.py",
        "test_issue5759_composer_focus_shortcut.py",
        "test_mobile_layout.py",
        "test_mobile_sidebar_header_icon_align.py",
        "test_pwa_manifest_sw.py",
        "test_pwa_sidebar_swipe.py",
        "test_real_steer.py",
        "test_session_batch_select.py",
        "test_session_public_share_static.py",
        "test_sidebar_search_highlights.py",
        "test_sidebar_unassigned_filter.py",
    }
    actual_files = {
        entry["nodeid"].split("::", 1)[0].rsplit("/", 1)[-1]
        for entry in manifest["replacements"]
    }
    assert actual_files == allowed_files
    assert not any(
        token in entry["nodeid"]
        for entry in manifest["replacements"]
        for token in ("api", "server", "auth", "storage", "package", "docker", "mcp")
    )


def test_order_sensitive_manifest_is_pinned_mandatory_and_separate():
    module = _runner_module()
    isolated = module.load_isolated_tests()
    upstream = json.loads((ROOT / "UPSTREAM.json").read_text(encoding="utf-8"))
    manifest = json.loads(ISOLATED_MANIFEST_PATH.read_text(encoding="utf-8"))
    replacements = {entry["nodeid"] for entry in module.load_replacements()}

    assert manifest["upstream_commit"] == upstream["commit"]
    assert len(isolated) == 1
    assert isolated[0]["nodeid"] not in replacements
    assert isolated[0]["nodeid"].startswith("tests/test_issue5220_")
    assert "fresh" in isolated[0]["reason"]


def test_order_sensitive_node_runs_once_per_unsharded_or_shard_zero(monkeypatch):
    module = _runner_module()
    calls = []

    def fake_call(command, cwd):
        calls.append((command, cwd))
        return 0

    monkeypatch.setattr(module.subprocess, "call", fake_call)

    assert module.main(["tests/", "--shard-id=0", "--num-shards=5"]) == 0
    assert len(calls) == 2
    isolated_nodeid = module.load_isolated_tests()[0]["nodeid"]
    assert f"--deselect={isolated_nodeid}" in calls[0][0]
    assert isolated_nodeid in calls[1][0]

    calls.clear()
    assert module.main(["tests/", "--shard-id=1", "--num-shards=5"]) == 0
    assert len(calls) == 1

    calls.clear()
    assert module.main(["tests/"]) == 0
    assert len(calls) == 2
