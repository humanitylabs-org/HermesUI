import importlib.util
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "hermesui" / "installer" / "stop-owned-process.py"
SPEC = importlib.util.spec_from_file_location("hermesui_stop_owned_process", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return path.resolve()


def test_upstream_bootstrap_interpreter_handoff_is_allowed_but_arbitrary_python_is_not(tmp_path):
    repo = tmp_path / "repo"
    agent = tmp_path / "agent"
    launch_python = executable(tmp_path / "system" / "python3")
    agent_python = executable(agent / "venv" / "bin" / "python")
    rogue_python = executable(tmp_path / "rogue" / "python")

    allowed = MODULE.allowed_runtime_executables(
        repo,
        {"HERMES_WEBUI_AGENT_DIR": str(agent)},
        launch_python,
    )

    assert launch_python in allowed
    assert agent_python in allowed
    assert rogue_python not in allowed


def test_repository_venv_handoff_is_allowed(tmp_path):
    repo = tmp_path / "repo"
    launch_python = executable(tmp_path / "system" / "python3")
    repo_python = executable(repo / ".venv" / "bin" / "python")

    allowed = MODULE.allowed_runtime_executables(repo, {}, launch_python)

    assert allowed == frozenset({launch_python, repo_python})


def test_agent_directory_must_be_absolute_and_existing(tmp_path):
    launch_python = executable(tmp_path / "system" / "python3")

    with pytest.raises(RuntimeError, match="not absolute"):
        MODULE.allowed_runtime_executables(
            tmp_path / "repo",
            {"HERMES_WEBUI_AGENT_DIR": "relative/agent"},
            launch_python,
        )

    with pytest.raises(FileNotFoundError):
        MODULE.allowed_runtime_executables(
            tmp_path / "repo",
            {"HERMES_WEBUI_AGENT_DIR": str(tmp_path / "missing-agent")},
            launch_python,
        )


@pytest.mark.skipif(not Path("/proc/self/exe").exists(), reason="requires Linux procfs")
def test_full_process_verifier_accepts_upstream_exec_into_agent_venv(tmp_path):
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    agent = tmp_path / "agent"
    repo.mkdir()
    home.mkdir()
    agent_python = agent / "venv" / "bin" / "python"
    agent_python.parent.mkdir(parents=True)
    shutil.copy2(sys.executable, agent_python)
    agent_python.chmod(0o700)
    (repo / "bootstrap.py").write_text("# bootstrap fixture\n", encoding="utf-8")
    server = repo / "server.py"
    server.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")

    launch_python, managed_path = MODULE.managed_python_executable(home)
    commit = "1" * 40
    tree = "2" * 40
    port = 18793
    env = os.environ.copy()
    env.update(
        {
            "HERMESUI_MANAGED": "1",
            "HERMESUI_RUNTIME_COMMIT": commit,
            "HERMESUI_RUNTIME_TREE": tree,
            "HERMES_WEBUI_PYTHON": str(launch_python),
            "HERMES_WEBUI_AGENT_DIR": str(agent),
            "HOME": str(home),
            "PATH": managed_path,
            "HERMES_WEBUI_HOST": "127.0.0.1",
            "HERMES_WEBUI_PORT": str(port),
        }
    )
    process = subprocess.Popen([str(agent_python), str(server)], cwd=agent, env=env)
    try:
        for _ in range(100):
            if Path(f"/proc/{process.pid}/exe").exists():
                break
            time.sleep(0.01)
        MODULE.verify_owned_process(
            process.pid,
            repo,
            home,
            port,
            allowed_runtime_identities=frozenset({(commit, tree)}),
        )
    finally:
        process.terminate()
        process.wait(timeout=5)
