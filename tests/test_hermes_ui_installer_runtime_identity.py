import importlib.util
import os
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
    home = tmp_path / "home"
    agent = tmp_path / "hermes-agent"
    home.mkdir()
    agent.mkdir()
    (agent / "run_agent.py").write_text("# agent fixture\n", encoding="utf-8")
    launch_python = executable(tmp_path / "system" / "python3")
    agent_python = executable(agent / "venv" / "bin" / "python")
    rogue_python = executable(tmp_path / "rogue" / "python")
    roots = MODULE.trusted_agent_roots(repo, home, "/usr/local/bin:/usr/bin:/bin", launch_python)

    allowed = MODULE.allowed_runtime_executables(
        repo,
        launch_python,
        roots,
    )

    assert launch_python in allowed
    assert agent_python in allowed
    assert rogue_python not in allowed


def test_repository_venv_handoff_is_allowed(tmp_path):
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    launch_python = executable(tmp_path / "system" / "python3")
    repo_python = executable(repo / ".venv" / "bin" / "python")

    allowed = MODULE.allowed_runtime_executables(repo, launch_python, frozenset())

    assert allowed == frozenset({launch_python, repo_python})


@pytest.mark.skipif(not Path("/proc/self/exe").exists(), reason="requires Linux procfs")
def test_target_process_cannot_self_nominate_a_foreign_agent_runtime(tmp_path):
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    foreign_agent = tmp_path / "attacker-controlled-agent"
    repo.mkdir()
    home.mkdir()
    foreign_python = foreign_agent / "venv" / "bin" / "python"
    foreign_python.parent.mkdir(parents=True)
    foreign_python.symlink_to(Path(sys.executable).resolve())
    (foreign_agent / "run_agent.py").write_text("# attacker fixture\n", encoding="utf-8")
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
            "HERMES_WEBUI_AGENT_DIR": str(foreign_agent),
            "HOME": str(home),
            "PATH": managed_path,
            "HERMES_WEBUI_HOST": "127.0.0.1",
            "HERMES_WEBUI_PORT": str(port),
        }
    )
    process = subprocess.Popen([str(foreign_python), str(server)], cwd=foreign_agent, env=env)
    try:
        with pytest.raises(RuntimeError, match="not independently discovered"):
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


@pytest.mark.skipif(not Path("/proc/self/exe").exists(), reason="requires Linux procfs")
def test_full_process_verifier_accepts_upstream_exec_into_agent_venv(tmp_path):
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    agent = tmp_path / "hermes-agent"
    repo.mkdir()
    home.mkdir()
    agent_python = agent / "venv" / "bin" / "python"
    agent_python.parent.mkdir(parents=True)
    agent_python.symlink_to(Path(sys.executable).resolve())
    (agent / "run_agent.py").write_text("# agent fixture\n", encoding="utf-8")
    (repo / "bootstrap.py").write_text("# bootstrap fixture\n", encoding="utf-8")
    server = repo / "server.py"
    server.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")

    launch_python, managed_path = MODULE.managed_python_executable(home)
    commit = "1" * 40
    tree = "2" * 40
    port = 18793
    hermes_home = tmp_path / "runtime-home"
    env = os.environ.copy()
    env.update(
        {
            "HERMESUI_MANAGED": "1",
            "HERMESUI_MODE": "standalone",
            "HERMESUI_PROFILE": "default",
            "HERMESUI_RUNTIME_COMMIT": commit,
            "HERMESUI_RUNTIME_TREE": tree,
            "HERMES_WEBUI_PYTHON": str(launch_python),
            "HERMES_WEBUI_AGENT_DIR": str(agent),
            "HOME": str(home),
            "HERMES_HOME": str(hermes_home),
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
            hermes_home=hermes_home,
            profile="default",
        )
        with pytest.raises(RuntimeError, match="HERMES_HOME ownership check"):
            MODULE.verify_owned_process(
                process.pid,
                repo,
                home,
                port,
                hermes_home=tmp_path / "different-runtime-home",
                profile="default",
            )
    finally:
        process.terminate()
        process.wait(timeout=5)
