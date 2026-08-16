import json
import sys
from pathlib import Path

import bootstrap


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_name_and_tailnet_path_are_consistent():
    assert read("VERSION").strip() == "0.1.0"
    manifest = json.loads(read("static/manifest.json"))
    assert manifest["name"] == "HermesUI"
    assert manifest["short_name"] == "HermesUI"
    assert manifest["id"] == "./"
    assert manifest["start_url"].startswith("./")
    assert manifest["scope"] == "./"

    for path in (
        "README.md",
        "SECURITY.md",
        "docs/Tailnet-HermesUI-Prompt.md",
        "docs/give-this-prompt-to-your-ai.md",
        "scripts/tailnet-setup.sh",
        "scripts/tailnet-status.sh",
        "scripts/tailnet-uninstall.sh",
    ):
        text = read(path)
        assert "HermesUI" in text
        assert "/hermesUI" in text


def test_public_repository_links_point_to_hermesui():
    metadata = read("pyproject.toml")
    shell = read("static/index.html")
    repo_url = "https://github.com/humanitylabs-org/HermesUI"
    assert f'Repository = "{repo_url}"' in metadata
    assert f'Issues = "{repo_url}/issues"' in metadata
    assert f'href="{repo_url}/issues"' in shell


def test_installer_is_private_and_never_enables_funnel():
    setup = read("scripts/tailnet-setup.sh")
    serve_cas = read("scripts/tailscale-serve-cas.py")
    unit_contract = read("qa/tailnet-installer-smoke.sh")
    prompt = read("docs/give-this-prompt-to-your-ai.md")
    assert 'HOST="127.0.0.1"' in setup
    assert '"$SERVE_CAS" "${args[@]}"' in setup
    assert 'serve --bg --https=443 --set-path="$BASE_PATH"' not in setup
    assert '"If-Match": etag' in serve_cas
    assert '"/localapi/v0/serve-config"' in serve_cas
    assert '"$TAILSCALE" funnel' not in setup
    assert "assert_no_funnel" in setup
    assert "HERMES_WEBUI_HOST=127.0.0.1" in unit_contract
    assert "Never enable Funnel" in prompt


def test_installer_refuses_collisions_and_only_removes_its_own_route():
    setup = read("scripts/tailnet-setup.sh")
    status = read("scripts/tailnet-status.sh")
    uninstall = read("scripts/tailnet-uninstall.sh")
    smoke = read("qa/tailnet-installer-smoke.sh")
    assert "already in use by a process not managed by" in setup
    assert "already belongs to a different handler" in setup
    assert "serve status --json" in setup
    assert "install.env" in setup
    assert "serve status --json" in status
    assert "points to another handler, so it was preserved" in uninstall
    assert "Port collision test unexpectedly succeeded" in smoke
    assert "Serve collision test unexpectedly succeeded" in smoke
    assert "Foreground Serve collision test unexpectedly succeeded" in smoke
    assert "Unit collision test unexpectedly succeeded" in smoke
    assert "Funnel collision test unexpectedly succeeded" in smoke


def test_installer_lifecycle_is_parser_verified_and_fail_closed():
    prereq = read("scripts/tailnet-prereq-check.sh")
    setup = read("scripts/tailnet-setup.sh")
    status = read("scripts/tailnet-status.sh")
    uninstall = read("scripts/tailnet-uninstall.sh")
    starter = read("scripts/systemd-start-owned.py")
    launcher = read("scripts/systemd-launcher-unit.py")
    smoke = read("qa/tailnet-installer-smoke.sh")
    readme = read("README.md")
    assert "'tailscale up'" in prereq
    assert "`tailscale up`" not in prereq
    assert "# Managed by HermesUI Tailnet installer" in launcher
    assert "systemd-launcher-unit.py" in setup
    assert 'systemd-start-owned.py' in setup
    assert '"$SYSTEMD_ANALYZE" --user verify' in setup
    assert 'start_owned_service' in setup
    assert 'systemctl' not in starter
    assert 'StartTransientUnit' in starter
    assert '"--collect"' in starter
    assert '"--property=Restart=on-failure"' in starter
    assert "assert_no_funnel" in setup
    assert "AllowFunnel" in status
    assert "uninstall incomplete" in uninstall
    assert '"$PROCESS_STOP" --pid "$main_pid"' in uninstall
    assert '--systemd-unit "$SERVICE_NAME"' in uninstall
    assert '--systemctl "$SYSTEMCTL"' in uninstall
    assert "service cgroup" in read("scripts/stop-owned-process.py")
    assert 'properties["Transient"] != "yes"' in read("scripts/stop-owned-process.py")
    assert 'properties["FragmentPath"] != expected_fragment' in read("scripts/stop-owned-process.py")
    assert "disable --now" not in uninstall
    assert "Owned-process stop failure test unexpectedly succeeded" in smoke
    assert "Unit removal failure test unexpectedly succeeded" in smoke
    assert "Daemon-reload failure test unexpectedly succeeded" in smoke
    assert "Route removal failure test unexpectedly succeeded" in smoke
    assert 'unset HERMESUI_PORT' in smoke
    assert "https://<this-device>.ts.net/hermesUI/" in readme


def test_release_prompt_is_tag_pinned_and_verifiable():
    prompt = read("docs/Tailnet-HermesUI-Prompt.md")
    assert read("docs/give-this-prompt-to-your-ai.md") == prompt
    assert "reviewed tag `v0.1.0`" in prompt
    assert "git describe --tags --exact-match" in prompt
    assert "v0.1.0^{commit}" in prompt
    assert "git rev-parse HEAD" in prompt
    assert "git ls-remote origin" in prompt
    assert "Do not claim success until every check passes" in prompt
    assert "tailnet-uninstall.sh" in prompt
    assert "https://<this-device>.ts.net/hermesUI/" in prompt


def test_installed_package_fallback_uses_metadata_dependencies_and_cache(tmp_path, monkeypatch):
    installed_root = tmp_path / "site-packages"
    installed_root.mkdir()
    cache = tmp_path / "cache"
    venv_python = cache / "hermes-webui" / f"venv-py{sys.version_info.major}{sys.version_info.minor}" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")
    calls = []
    checks = iter([False, True])
    monkeypatch.setattr(bootstrap, "REPO_ROOT", installed_root)
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    monkeypatch.setattr(bootstrap.importlib.metadata, "requires", lambda name: ["PyYAML>=6", "fastapi>=0.100"])
    monkeypatch.setattr(bootstrap, "_python_can_run_webui_and_agent", lambda *args: next(checks))
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda command, **kwargs: calls.append(command))

    selected = bootstrap.ensure_python_has_webui_deps("/usr/bin/python3")

    assert selected == str(venv_python)
    assert calls[-1][-2:] == ["PyYAML>=6", "fastapi>=0.100"]
    assert "-r" not in calls[-1]
