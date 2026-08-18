from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
FULL_GATES = (
    "tests.yml",
    "browser-smoke.yml",
    "conversation-lifecycle.yml",
    "docker-smoke.yml",
    "docs-ci.yml",
)


def test_inherited_full_gates_are_reachable_from_downstream_main():
    for name in FULL_GATES:
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert text.count("branches: [main, master, hermes-ui]") == 2, name
        assert "branches: [master, hermes-ui]" not in text, name


def test_diff_fallbacks_and_ruff_gate_use_live_default_branch():
    for name in ("tests.yml", "browser-smoke.yml", "docs-ci.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "origin hermes-ui" not in text, name
        assert "origin main" in text, name

    tests_workflow = (WORKFLOWS / "tests.yml").read_text(encoding="utf-8")
    assert "scripts/ruff_lint.py --diff origin/main" in tests_workflow
    assert "scripts/ruff_lint.py --diff origin/hermes-ui" not in tests_workflow
