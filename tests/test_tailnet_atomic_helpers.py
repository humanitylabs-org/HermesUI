"""Direct contracts for the atomic Tailnet lifecycle helpers."""

from __future__ import annotations

import errno
import hashlib
import http.server
import importlib.util
import json
import os
import shutil
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATH_OP = ROOT / "scripts" / "owned-path-op.py"
SERVE_CAS = ROOT / "scripts" / "tailscale-serve-cas.py"
STOP_PROCESS = ROOT / "scripts" / "stop-owned-process.py"
START_SERVICE = ROOT / "scripts" / "systemd-start-owned.py"
LAUNCHER_UNIT = ROOT / "scripts" / "systemd-launcher-unit.py"
TAILNET_STATUS = ROOT / "scripts" / "tailnet-status.sh"
LISTENER = "device.tailnet.example.ts.net:443"
MOUNT = "/hermesUI"
TARGET = "http://127.0.0.1:8793"
MANAGED_HOME = Path.home().resolve()
MANAGED_PATH = f"{MANAGED_HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin"
_managed_python = shutil.which("python3", path=MANAGED_PATH)
assert _managed_python is not None
MANAGED_PYTHON = Path(_managed_python).resolve()


def _managed_process_env(port: int) -> dict[str, str]:
    return {
        "HERMESUI_MANAGED": "1",
        "HERMES_WEBUI_PYTHON": str(MANAGED_PYTHON),
        "HOME": str(MANAGED_HOME),
        "PATH": MANAGED_PATH,
        "HERMES_WEBUI_HOST": "127.0.0.1",
        "HERMES_WEBUI_PORT": str(port),
    }


def test_systemd_start_helper_passes_exact_transient_contract(tmp_path: Path) -> None:
    log = tmp_path / "args.json"
    fake = tmp_path / "systemd-run"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "open(os.environ['START_LOG'], 'w', encoding='utf-8').write(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = {**os.environ, "START_LOG": str(log)}

    result = subprocess.run(
        [
            sys.executable,
            str(START_SERVICE),
            "--systemd-run",
            str(fake),
            "--unit",
            "hermesui.service",
            "--repo-root",
            str(ROOT),
            "--home",
            str(tmp_path),
            "--port",
            "18793",
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    args = json.loads(log.read_text(encoding="utf-8"))
    assert "--unit=hermesui.service" in args
    assert "--collect" in args
    assert "--service-type=exec" in args
    assert "--property=Restart=on-failure" in args
    assert "--setenv=HERMESUI_MANAGED=1" in args
    managed_path = f"{tmp_path}/.local/bin:/usr/local/bin:/usr/bin:/bin"
    managed_python = shutil.which("python3", path=managed_path)
    assert managed_python is not None
    managed_python = str(Path(managed_python).resolve())
    assert f"--setenv=HERMES_WEBUI_PYTHON={managed_python}" in args
    assert "--setenv=HERMES_WEBUI_HOST=127.0.0.1" in args
    assert "--setenv=HERMES_WEBUI_PORT=18793" in args
    assert "--setenv=HERMES_WEBUI_COOKIE_PATH=/hermesUI" in args
    assert str((ROOT / "bootstrap.py").resolve()) in args
    assert managed_python in args


def test_systemd_start_helper_rejects_unexpected_unit_before_provider_call(tmp_path: Path) -> None:
    marker = tmp_path / "called"
    fake = tmp_path / "systemd-run"
    fake.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
    fake.chmod(0o755)

    result = subprocess.run(
        [
            sys.executable,
            str(START_SERVICE),
            "--systemd-run",
            str(fake),
            "--unit",
            "foreign.service",
            "--repo-root",
            str(ROOT),
            "--home",
            str(tmp_path),
            "--port",
            "18793",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert not marker.exists()


def test_launcher_unit_verifier_requires_exact_managed_bytes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    repo.mkdir()
    (repo / "scripts").mkdir()
    (repo / "scripts" / "systemd-start-owned.py").write_text("", encoding="utf-8")
    home.mkdir()
    unit = tmp_path / "hermesui-launcher.service"
    common = [
        "--repo-root", str(repo),
        "--home", str(home),
        "--host", "127.0.0.1",
        "--port", "18892",
    ]
    written = subprocess.run(
        [sys.executable, str(LAUNCHER_UNIT), "write", str(unit), *common],
        text=True, capture_output=True, check=False,
    )
    assert written.returncode == 0, written.stderr
    verified = subprocess.run(
        [sys.executable, str(LAUNCHER_UNIT), "verify", str(unit), *common],
        text=True, capture_output=True, check=False,
    )
    assert verified.returncode == 0, verified.stderr

    unit.write_text(
        unit.read_text(encoding="utf-8").replace(
            "ExecStart=/usr/bin/env python3",
            "ExecStart=/bin/sh -c foreign",
            1,
        ),
        encoding="utf-8",
    )
    refused = subprocess.run(
        [sys.executable, str(LAUNCHER_UNIT), "verify", str(unit), *common],
        text=True, capture_output=True, check=False,
    )
    assert refused.returncode == 1
    assert "bytes" in refused.stderr


def test_status_rejects_foreign_launcher_fragment_even_with_marker(tmp_path: Path) -> None:
    state = tmp_path / "state"
    systemd_dir = tmp_path / "systemd"
    foreign_dir = tmp_path / "foreign"
    bindir = tmp_path / "bin"
    for path in (state, systemd_dir, foreign_dir, bindir):
        path.mkdir()
    (state / "install.env").write_text(
        "HERMESUI_PORT=18893\nHERMESUI_TCP_443_CREATED=1\n",
        encoding="utf-8",
    )
    foreign = foreign_dir / "rogue-launcher.service"
    foreign.write_text(
        "# Managed by HermesUI Tailnet installer\n"
        "[Service]\n"
        "Environment=\"HERMES_WEBUI_HOST=127.0.0.1\"\n"
        "Environment=\"HERMES_WEBUI_PORT=18893\"\n"
        "ExecStart=/bin/sh -c foreign\n",
        encoding="utf-8",
    )
    systemctl = bindir / "systemctl"
    systemctl.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$FAKE_FOREIGN_UNIT\"\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)
    result = subprocess.run(
        [str(TAILNET_STATUS)],
        env={
            **os.environ,
            "HERMESUI_STATE_DIR": str(state),
            "HERMESUI_SYSTEMD_DIR": str(systemd_dir),
            "HERMESUI_SYSTEMCTL": str(systemctl),
            "FAKE_FOREIGN_UNIT": str(foreign),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "exact managed unit path" in result.stderr
    assert "HermesUI URL:" not in result.stdout


def run_path_op(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PATH_OP), *(str(arg) for arg in args)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_path_digest_refuses_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("owned", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(target)

    result = run_path_op("digest", link)

    assert result.returncode == 1
    assert "symlink" in result.stderr.lower() or "too many levels" in result.stderr.lower()
    assert target.read_text(encoding="utf-8") == "owned"


def test_fresh_publish_never_clobbers_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "candidate"
    destination = tmp_path / "managed"
    source.write_text("candidate", encoding="utf-8")
    destination.write_text("foreign", encoding="utf-8")

    result = run_path_op("publish", source, destination)

    assert result.returncode == 1
    assert destination.read_text(encoding="utf-8") == "foreign"
    assert source.read_text(encoding="utf-8") == "candidate"


def test_expected_mismatch_preserves_foreign_bytes(tmp_path: Path) -> None:
    destination = tmp_path / "managed"
    destination.write_text("foreign", encoding="utf-8")
    stale_digest = hashlib.sha256(b"owned-before").hexdigest()

    result = run_path_op("remove", destination, "--expected", stale_digest)

    assert result.returncode == 1
    assert "ownership changed at mutation boundary" in result.stderr
    assert destination.read_text(encoding="utf-8") == "foreign"


def test_expected_publish_replaces_only_exact_owned_preimage(tmp_path: Path) -> None:
    source = tmp_path / "candidate"
    destination = tmp_path / "managed"
    source.write_text("candidate", encoding="utf-8")
    destination.write_text("owned-before", encoding="utf-8")
    expected = hashlib.sha256(b"owned-before").hexdigest()

    result = run_path_op("publish", source, destination, "--expected", expected)

    assert result.returncode == 0, result.stderr
    assert destination.read_text(encoding="utf-8") == "candidate"
    assert not source.exists()


def _load_path_op():
    spec = importlib.util.spec_from_file_location("hermesui_owned_path_op", PATH_OP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_publish_cleanup_failure_restores_source_and_destination(tmp_path: Path, monkeypatch) -> None:
    module = _load_path_op()
    source = tmp_path / "candidate"
    destination = tmp_path / "managed"
    source.write_text("candidate-after", encoding="utf-8")
    destination.write_text("owned-before", encoding="utf-8")
    expected = hashlib.sha256(b"owned-before").hexdigest()
    original_unlink = Path.unlink

    def fail_quarantine(path: Path, *args, **kwargs):
        if ".hermesui-quarantine-" in path.name:
            raise OSError(errno.EIO, "injected quarantine unlink failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_quarantine)
    with pytest.raises(RuntimeError, match="original state was restored"):
        module.publish(source, destination, expected)
    assert source.read_text(encoding="utf-8") == "candidate-after"
    assert destination.read_text(encoding="utf-8") == "owned-before"


def test_remove_cleanup_failure_restores_destination(tmp_path: Path, monkeypatch) -> None:
    module = _load_path_op()
    destination = tmp_path / "managed"
    destination.write_text("owned-before", encoding="utf-8")
    expected = hashlib.sha256(b"owned-before").hexdigest()
    original_unlink = Path.unlink

    def fail_quarantine(path: Path, *args, **kwargs):
        if ".hermesui-quarantine-" in path.name:
            raise OSError(errno.EIO, "injected quarantine unlink failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_quarantine)
    with pytest.raises(RuntimeError, match="original state was restored"):
        module.remove(destination, expected)
    assert destination.read_text(encoding="utf-8") == "owned-before"


def test_symlink_create_and_remove_use_exact_target_contract(tmp_path: Path) -> None:
    destination = tmp_path / "default.target.wants" / "hermesui.service"
    target = str(tmp_path / "hermesui.service")
    Path(target).write_text("owned", encoding="utf-8")
    target_digest = hashlib.sha256(b"owned").hexdigest()

    created = run_path_op(
        "symlink-create", target, destination,
        "--expected-target-digest", target_digest,
    )
    assert created.returncode == 0, created.stderr
    assert destination.is_symlink()
    assert os.readlink(destination) == target

    mismatch = run_path_op("symlink-remove", destination, "--expected-target", "/foreign/unit")
    assert mismatch.returncode == 1
    assert destination.is_symlink()
    assert os.readlink(destination) == target

    removed = run_path_op(
        "symlink-remove", destination, "--expected-target", target,
        "--expected-target-digest", target_digest,
    )
    assert removed.returncode == 0, removed.stderr
    assert not destination.exists() and not destination.is_symlink()


def test_symlink_operations_preserve_pair_when_target_changes_at_entry(tmp_path: Path) -> None:
    destination = tmp_path / "default.target.wants" / "hermesui.service"
    target = tmp_path / "hermesui.service"
    target.write_text("owned", encoding="utf-8")
    owned_digest = hashlib.sha256(b"owned").hexdigest()
    target.write_text("foreign", encoding="utf-8")

    refused_create = run_path_op(
        "symlink-create", target, destination,
        "--expected-target-digest", owned_digest,
    )
    assert refused_create.returncode == 1
    assert not destination.exists() and not destination.is_symlink()

    destination.parent.mkdir(parents=True)
    destination.symlink_to(target)
    refused_remove = run_path_op(
        "symlink-remove", destination, "--expected-target", target,
        "--expected-target-digest", owned_digest,
    )
    assert refused_remove.returncode == 1
    assert destination.is_symlink()
    assert os.readlink(destination) == str(target)
    assert target.read_text(encoding="utf-8") == "foreign"


def test_symlink_cleanup_failure_restores_link(tmp_path: Path, monkeypatch) -> None:
    module = _load_path_op()
    destination = tmp_path / "hermesui.service"
    target = str(tmp_path / "owned.service")
    destination.symlink_to(target)
    original_unlink = Path.unlink

    def fail_quarantine(path: Path, *args, **kwargs):
        if ".hermesui-quarantine-" in path.name:
            raise OSError(errno.EIO, "injected symlink quarantine unlink failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_quarantine)
    with pytest.raises(RuntimeError, match="original link was restored"):
        module.remove_symlink(destination, target)
    assert destination.is_symlink()
    assert os.readlink(destination) == target


def test_stop_helper_terminates_only_matching_managed_process(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    bootstrap = repo / "bootstrap.py"
    bootstrap.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    port = 18888
    env = os.environ.copy()
    env.update(_managed_process_env(port))
    process = subprocess.Popen(
        [
            str(MANAGED_PYTHON),
            str(bootstrap),
            str(port),
            "--host",
            "127.0.0.1",
            "--no-browser",
            "--foreground",
            "--skip-agent-install",
        ],
        env=env,
        cwd=repo,
    )
    try:
        verified = subprocess.run(
            [
                sys.executable,
                str(STOP_PROCESS),
                "--pid",
                str(process.pid),
                "--repo-root",
                str(repo),
                "--home",
                str(MANAGED_HOME),
                "--port",
                str(port),
                "--verify-only",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert verified.returncode == 0, verified.stderr
        assert process.poll() is None

        result = subprocess.run(
            [
                sys.executable,
                str(STOP_PROCESS),
                "--pid",
                str(process.pid),
                "--repo-root",
                str(repo),
                "--home",
                str(MANAGED_HOME),
                "--port",
                str(port),
                "--timeout",
                "2",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert process.wait(timeout=2) == -15
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=2)


def test_stop_helper_refuses_unmanaged_process(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    bootstrap = repo / "bootstrap.py"
    bootstrap.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    port = 18889
    process = subprocess.Popen(
        [sys.executable, str(bootstrap), str(port), "--host", "127.0.0.1", "--foreground"]
    )
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(STOP_PROCESS),
                "--pid",
                str(process.pid),
                "--repo-root",
                str(repo),
                "--home",
                str(MANAGED_HOME),
                "--port",
                str(port),
                "--timeout",
                "2",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 1
        assert "HERMESUI_MANAGED" in result.stderr
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=2)


def test_stop_helper_accepts_exact_exec_handoff_server_form(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "bootstrap.py").write_text("", encoding="utf-8")
    server = repo / "server.py"
    server.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    port = 18890
    env = os.environ.copy()
    env.update(_managed_process_env(port))
    process = subprocess.Popen([str(MANAGED_PYTHON), str(server)], env=env, cwd=repo)
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(STOP_PROCESS),
                "--pid",
                str(process.pid),
                "--repo-root",
                str(repo),
                "--home",
                str(MANAGED_HOME),
                "--port",
                str(port),
                "--verify-only",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=2)


def test_stop_helper_refuses_foreign_executable_with_exact_server_argv(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "bootstrap.py").write_text("", encoding="utf-8")
    server = repo / "server.py"
    os.mkfifo(server)
    foreign = shutil.which("cat")
    assert foreign is not None
    port = 18894
    env = os.environ.copy()
    env.update(_managed_process_env(port))
    process = subprocess.Popen([foreign, str(server)], env=env, cwd=repo)
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(STOP_PROCESS),
                "--pid",
                str(process.pid),
                "--repo-root",
                str(repo),
                "--home",
                str(MANAGED_HOME),
                "--port",
                str(port),
                "--verify-only",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 1
        assert "exact managed Python interpreter" in result.stderr
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=2)


def test_stop_helper_does_not_trust_process_controlled_home_for_python(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "bootstrap.py").write_text("", encoding="utf-8")
    server = repo / "server.py"
    os.mkfifo(server)
    foreign = Path(shutil.which("cat") or "")
    assert foreign.is_file()
    hostile_home = tmp_path / "hostile-home"
    hostile_bin = hostile_home / ".local/bin"
    hostile_bin.mkdir(parents=True)
    hostile_python = hostile_bin / "python3"
    hostile_python.symlink_to(foreign)
    port = 18895
    env = os.environ.copy()
    env.update(_managed_process_env(port))
    env.update({"HOME": str(hostile_home)})
    process = subprocess.Popen([str(hostile_python), str(server)], env=env, cwd=repo)
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(STOP_PROCESS),
                "--pid",
                str(process.pid),
                "--repo-root",
                str(repo),
                "--home",
                str(MANAGED_HOME),
                "--port",
                str(port),
                "--verify-only",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 1
        assert "HOME ownership check" in result.stderr
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=2)


def test_stop_helper_refuses_managed_token_membership_spoof(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    bootstrap = repo / "bootstrap.py"
    bootstrap.write_text("", encoding="utf-8")
    (repo / "server.py").write_text("", encoding="utf-8")
    port = 18891
    env = os.environ.copy()
    env.update(_managed_process_env(port))
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            str(bootstrap),
            str(port),
            "--host",
            "127.0.0.1",
            "--foreground",
            "--foreign-extra",
        ],
        env=env,
        cwd=repo,
    )
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(STOP_PROCESS),
                "--pid",
                str(process.pid),
                "--repo-root",
                str(repo),
                "--home",
                str(MANAGED_HOME),
                "--port",
                str(port),
                "--timeout",
                "2",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 1
        assert "argv" in result.stderr
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=2)


def _load_stop_process():
    spec = importlib.util.spec_from_file_location("hermesui_stop_owned_process", STOP_PROCESS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runtime_provider_systemctl(tmp_path: Path, *, pid: int, transient: str, fragment: str) -> Path:
    systemctl = tmp_path / "systemctl"
    systemctl.write_text(
        "#!/bin/sh\n"
        f"printf 'MainPID={pid}\\n'\n"
        f"printf 'Transient={transient}\\n'\n"
        f"printf 'FragmentPath={fragment}\\n'\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)
    return systemctl


def test_runtime_provider_requires_exact_transient_identity(tmp_path: Path) -> None:
    module = _load_stop_process()
    pid = 424242
    fragment = f"/run/user/{os.getuid()}/systemd/transient/hermesui.service"
    systemctl = _runtime_provider_systemctl(
        tmp_path,
        pid=pid,
        transient="yes",
        fragment=fragment,
    )

    module.verify_systemd_provider(pid, "hermesui.service", str(systemctl))


@pytest.mark.parametrize(
    ("pid", "transient", "fragment", "message"),
    [
        (7, "yes", "/run/user/0/systemd/transient/hermesui.service", "MainPID"),
        (424242, "no", "/run/user/0/systemd/user/hermesui.service", "not the managed transient"),
        (424242, "yes", "/run/user/0/systemd/user/hermesui.service", "fragment"),
    ],
)
def test_runtime_provider_rejects_foreign_or_changed_identity(
    tmp_path: Path,
    pid: int,
    transient: str,
    fragment: str,
    message: str,
) -> None:
    module = _load_stop_process()
    expected_pid = 424242
    if fragment.startswith("/run/user/0/"):
        fragment = fragment.replace("/run/user/0/", f"/run/user/{os.getuid()}/", 1)
    systemctl = _runtime_provider_systemctl(
        tmp_path,
        pid=pid,
        transient=transient,
        fragment=fragment,
    )

    with pytest.raises(RuntimeError, match=message):
        module.verify_systemd_provider(expected_pid, "hermesui.service", str(systemctl))


class _UnixHTTPServer(socketserver.UnixStreamServer):
    allow_reuse_address = True


class _ServeHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps(self.server.state["config"]).encode()  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("ETag", self.server.state["etag"])  # type: ignore[attr-defined]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        state = self.server.state  # type: ignore[attr-defined]
        state["posts"].append(
            {
                "if_match": self.headers.get("If-Match"),
                "body": json.loads(body),
            }
        )
        response = b""
        self.send_response(state["post_status"])
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()


@pytest.fixture
def serve_api(tmp_path: Path):
    servers: list[tuple[_UnixHTTPServer, threading.Thread]] = []

    def start(config: dict, *, post_status: int = 200, etag: str = '"rev-1"'):
        socket_path = tmp_path / f"tailscaled-{len(servers)}.sock"
        server = _UnixHTTPServer(str(socket_path), _ServeHandler)
        server.state = {  # type: ignore[attr-defined]
            "config": config,
            "etag": etag,
            "post_status": post_status,
            "posts": [],
        }
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return socket_path, server.state  # type: ignore[attr-defined]

    yield start

    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def run_serve_cas(socket_path: Path, expected: str, desired: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SERVE_CAS),
            "--socket",
            str(socket_path),
            "--listener",
            LISTENER,
            "--path",
            MOUNT,
            "--expected",
            expected,
            "--desired",
            desired,
            *extra,
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def test_serve_cas_adds_only_managed_route_and_sends_etag(serve_api) -> None:
    config = {
        "Web": {
            "other.tailnet.example.ts.net:443": {
                "Handlers": {"/": {"Proxy": "http://127.0.0.1:7000"}}
            }
        },
        "AllowFunnel": {},
    }
    socket_path, state = serve_api(config)

    result = run_serve_cas(socket_path, "absent", TARGET)

    assert result.returncode == 0, result.stderr
    assert len(state["posts"]) == 1
    post = state["posts"][0]
    assert post["if_match"] == '"rev-1"'
    assert post["body"]["Web"][LISTENER]["Handlers"][MOUNT] == {"Proxy": TARGET}
    assert post["body"]["Web"]["other.tailnet.example.ts.net:443"] == config["Web"][
        "other.tailnet.example.ts.net:443"
    ]
    assert post["body"]["TCP"]["443"] == {"HTTPS": True}


def test_serve_cas_route_conflict_fails_without_post(serve_api) -> None:
    config = {
        "Web": {LISTENER: {"Handlers": {MOUNT: {"Proxy": "http://127.0.0.1:7777"}}}}
    }
    socket_path, state = serve_api(config)

    result = run_serve_cas(socket_path, "absent", TARGET)

    assert result.returncode == 1
    assert "changed ownership" in result.stderr
    assert state["posts"] == []


@pytest.mark.parametrize(
    "handler",
    [
        None,
        "foreign",
        ["future-handler"],
        {"Path": "/foreign"},
        {"Text": "foreign"},
        {"Redirect": "https://example.com"},
        {"Proxy": TARGET, "Future": True},
    ],
)
def test_serve_cas_rejects_non_proxy_handler_without_post(serve_api, handler) -> None:
    config = {"Web": {LISTENER: {"Handlers": {MOUNT: handler}}}}
    socket_path, state = serve_api(config)

    result = run_serve_cas(socket_path, "absent", TARGET)

    assert result.returncode == 1
    assert "non-Proxy handler" in result.stderr
    assert state["posts"] == []


def test_serve_cas_rejects_foreground_ambiguity_without_post(serve_api) -> None:
    config = {
        "Foreground": {
            "outer": {
                "Foreground": {
                    "session": {"Web": {LISTENER: {"Handlers": {MOUNT: {"Proxy": TARGET}}}}}
                }
            }
        }
    }
    socket_path, state = serve_api(config)

    result = run_serve_cas(socket_path, "absent", TARGET)

    assert result.returncode == 1
    assert "foreground Serve ownership is ambiguous" in result.stderr
    assert state["posts"] == []


def test_serve_cas_stale_etag_failure_is_reported(serve_api) -> None:
    socket_path, state = serve_api({}, post_status=412)

    result = run_serve_cas(socket_path, "absent", TARGET)

    assert result.returncode == 1
    assert state["posts"][0]["if_match"] == '"rev-1"'
    assert "HTTP 412" in result.stderr


def test_serve_cas_removes_owned_route_but_preserves_other_handlers(serve_api) -> None:
    config = {
        "TCP": {"443": {"HTTPS": True}},
        "Web": {
            LISTENER: {
                "Handlers": {
                    MOUNT: {"Proxy": TARGET},
                    "/other": {"Proxy": "http://127.0.0.1:7000"},
                }
            }
        },
    }
    socket_path, state = serve_api(config)

    result = run_serve_cas(socket_path, TARGET, "absent", "--remove-tcp-if-owned")

    assert result.returncode == 0, result.stderr
    body = state["posts"][0]["body"]
    assert MOUNT not in body["Web"][LISTENER]["Handlers"]
    assert body["Web"][LISTENER]["Handlers"]["/other"] == {"Proxy": "http://127.0.0.1:7000"}
    assert body["TCP"]["443"] == {"HTTPS": True}
