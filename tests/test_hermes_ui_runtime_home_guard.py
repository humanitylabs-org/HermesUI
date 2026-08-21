import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = ROOT / "hermesui" / "installer" / "runtime-home-guard.py"
START_PATH = ROOT / "hermesui" / "installer" / "systemd-start-owned.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = load(GUARD_PATH, "hermesui_runtime_home_guard")
starter = load(START_PATH, "hermesui_systemd_start_owned")


def make_process(proc_root: Path, pid: int, *, argv: list[str], env: dict[str, str]) -> Path:
    pid_dir = proc_root / str(pid)
    pid_dir.mkdir(parents=True)
    (pid_dir / "cmdline").write_bytes(b"\0".join(item.encode() for item in argv) + b"\0")
    (pid_dir / "environ").write_bytes(
        b"\0".join(f"{key}={value}".encode() for key, value in env.items()) + b"\0"
    )
    return pid_dir


def make_webui_tree(tmp_path: Path) -> Path:
    repo = tmp_path / "webui"
    (repo / "api").mkdir(parents=True)
    (repo / "static").mkdir()
    (repo / "api" / "routes.py").write_text("# fixture\n", encoding="utf-8")
    (repo / "static" / "index.html").write_text("fixture\n", encoding="utf-8")
    (repo / "server.py").write_text("# fixture\n", encoding="utf-8")
    return repo


def test_shared_home_guard_rejects_webui_process_and_allows_exact_managed_pid(tmp_path):
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    webui = make_webui_tree(tmp_path)
    home = tmp_path / "home"
    hermes_home = home / ".hermes"
    pid = 42001
    make_process(
        proc_root,
        pid,
        argv=["/usr/bin/python3", str(webui / "server.py")],
        env={"HOME": str(home), "HERMES_WEBUI_PORT": "8793"},
    )

    with pytest.raises(RuntimeError, match="refusing to start a second"):
        guard.guard(hermes_home, proc_root=proc_root)

    guard.guard(hermes_home, proc_root=proc_root, allow_pids=frozenset({pid}))


def test_shared_home_guard_ignores_distinct_runtime_home(tmp_path):
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    webui = make_webui_tree(tmp_path)
    make_process(
        proc_root,
        42002,
        argv=["/usr/bin/python3", str(webui / "server.py")],
        env={"HOME": str(tmp_path / "other"), "HERMES_HOME": str(tmp_path / "other-hermes")},
    )

    assert guard.conflicting_processes(tmp_path / "target-hermes", proc_root=proc_root) == []


def test_likely_webui_with_unreadable_or_missing_home_fails_closed(tmp_path):
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    webui = make_webui_tree(tmp_path)
    make_process(
        proc_root,
        42003,
        argv=["/usr/bin/python3", str(webui / "server.py")],
        env={"HERMES_WEBUI_PORT": "8793"},
    )

    with pytest.raises(RuntimeError, match="no readable HOME or HERMES_HOME"):
        guard.guard(tmp_path / "target-hermes", proc_root=proc_root)


def test_unrelated_process_with_hermes_only_in_argument_is_not_a_conflict(tmp_path):
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    make_process(
        proc_root,
        42004,
        argv=["/usr/bin/chromium", "--user-data-dir=/tmp/hermes-private-manager-probe"],
        env={},
    )

    assert guard.conflicting_processes(tmp_path / "target-hermes", proc_root=proc_root) == []


def test_inherited_webui_environment_without_listener_is_not_execution_authority():
    assert not guard.likely_execution_process(
        ["node", "/home/user/.hermes/lsp/bin/typescript-language-server", "--stdio"],
        {"HERMES_WEBUI_PORT": "8793", "HERMESUI_MANAGED": "1"},
    )


def test_declared_webui_process_must_own_listener_for_environment_fallback(tmp_path):
    pid_dir = tmp_path / "proc" / "42005"
    (pid_dir / "fd").mkdir(parents=True)
    (pid_dir / "net").mkdir()
    (pid_dir / "fd" / "7").symlink_to("socket:[12345]")
    (pid_dir / "net" / "tcp").write_text(
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 0100007F:2259 00000000:0000 0A 00000000:00000000 00:00000000 00000000 1000 0 12345\n",
        encoding="ascii",
    )
    assert guard._process_owns_listener(pid_dir, "8793")
    assert guard.likely_execution_process(
        ["/usr/bin/python3", "-c", "serve_forever()"],
        {"HERMES_WEBUI_PORT": "8793"},
        owns_listener=True,
    )


def test_relative_server_entrypoint_is_resolved_from_process_cwd(tmp_path):
    webui = make_webui_tree(tmp_path)
    assert guard.likely_execution_process(
        ["/usr/bin/python3", "server.py"],
        {},
        cwd=webui,
    )


def test_systemd_runtime_starts_through_guard_with_persisted_home(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    hermes_home = tmp_path / "runtime-home"
    command = starter.build_command(
        "systemd-run",
        "hermesui.service",
        ROOT,
        home,
        hermes_home,
        "default",
        18993,
    )

    guard_path = str(GUARD_PATH.resolve())
    assert guard_path in command
    assert "exec" in command
    assert f"--setenv=HERMES_HOME={hermes_home}" in command
    assert "--setenv=HERMESUI_MODE=standalone" in command
    assert command[command.index("--hermes-home") + 1] == str(hermes_home)
    assert str((ROOT / "bootstrap.py").resolve()) not in command


def test_only_default_profile_is_supported(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    with pytest.raises(RuntimeError, match="only the default"):
        starter.build_command(
            "systemd-run",
            "hermesui.service",
            ROOT,
            home,
            tmp_path / "runtime-home",
            "other",
            18993,
        )
