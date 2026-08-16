#!/usr/bin/env python3
"""Stop only the exact running process owned by a HermesUI unit.

The caller supplies systemd's previously observed MainPID. A pidfd pins that
process identity before its environment and argv are verified, so PID reuse or
a same-name unit takeover cannot redirect the signal to another service.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import os
import select
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


SYS_PIDFD_SEND_SIGNAL = 424
SYS_PIDFD_OPEN = 434


def pidfd_open(pid: int) -> int:
    if hasattr(os, "pidfd_open"):
        return os.pidfd_open(pid, 0)  # type: ignore[attr-defined]
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.syscall(SYS_PIDFD_OPEN, pid, 0)
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return int(result)


def pidfd_send_signal(pidfd: int, sig: int) -> None:
    if hasattr(signal, "pidfd_send_signal"):
        signal.pidfd_send_signal(pidfd, sig)  # type: ignore[attr-defined]
        return
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.syscall(SYS_PIDFD_SEND_SIGNAL, pidfd, sig, 0, 0)
    if result < 0:
        error = ctypes.get_errno()
        if error == errno.ESRCH:
            return
        raise OSError(error, os.strerror(error))


def process_bytes(pid: int, name: str) -> bytes:
    return (Path("/proc") / str(pid) / name).read_bytes()


def parse_environ(raw: bytes) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in raw.split(b"\0"):
        if not item or b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        values[key.decode("utf-8", "strict")] = value.decode("utf-8", "strict")
    return values


def managed_python_executable(home: Path) -> tuple[Path, str]:
    """Return the exact interpreter and PATH selected by the launch contract."""
    home = home.resolve(strict=True)
    managed_path = f"{home}/.local/bin:/usr/local/bin:/usr/bin:/bin"
    python = shutil.which("python3", path=managed_path)
    if python is None:
        raise RuntimeError("python3 was not found in the managed launch PATH")
    executable = Path(python).resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise RuntimeError("managed Python interpreter is not executable")
    return executable, managed_path


def verify_owned_process(
    pid: int,
    repo_root: Path,
    home: Path,
    port: int,
    systemd_unit: str | None = None,
) -> None:
    proc = Path("/proc") / str(pid)
    if proc.stat().st_uid != os.getuid():
        raise RuntimeError("service process is owned by another user")

    environ = parse_environ(process_bytes(pid, "environ"))
    expected_python, managed_path = managed_python_executable(home)
    required_env = {
        "HERMESUI_MANAGED": "1",
        "HERMES_WEBUI_PYTHON": str(expected_python),
        "HOME": str(home.resolve(strict=True)),
        "PATH": managed_path,
        "HERMES_WEBUI_HOST": "127.0.0.1",
        "HERMES_WEBUI_PORT": str(port),
    }
    for key, expected in required_env.items():
        if environ.get(key) != expected:
            raise RuntimeError(f"service process failed the {key} ownership check")

    argv = [part.decode("utf-8", "strict") for part in process_bytes(pid, "cmdline").split(b"\0") if part]
    bootstrap = str((repo_root / "bootstrap.py").resolve())
    server = str((repo_root / "server.py").resolve())
    bootstrap_form = argv[1:] == [
        bootstrap,
        str(port),
        "--host",
        "127.0.0.1",
        "--no-browser",
        "--foreground",
        "--skip-agent-install",
    ]
    server_form = argv[1:] == [server]
    if not bootstrap_form and not server_form:
        raise RuntimeError("service process argv does not match the managed HermesUI bootstrap or server")

    executable = (proc / "exe").resolve(strict=True)
    if executable != expected_python:
        raise RuntimeError("HermesUI executable is not the exact managed Python interpreter")
    argv_executable = shutil.which(argv[0], path=managed_path)
    if argv_executable is None or executable != Path(argv_executable).resolve(strict=True):
        raise RuntimeError("HermesUI executable identity does not match argv and PATH")
    if systemd_unit is not None:
        if systemd_unit != "hermesui.service":
            raise RuntimeError("unexpected HermesUI systemd unit name")
        cgroup_lines = process_bytes(pid, "cgroup").decode("utf-8", "strict").splitlines()
        if not any(line.split(":", 2)[-1].endswith(f"/{systemd_unit}") for line in cgroup_lines):
            raise RuntimeError("HermesUI process is not inside the managed systemd service cgroup")


def verify_systemd_provider(pid: int, systemd_unit: str, systemctl: str) -> None:
    if systemd_unit != "hermesui.service":
        raise RuntimeError("unexpected HermesUI systemd unit name")
    result = subprocess.run(
        [
            systemctl,
            "--user",
            "show",
            systemd_unit,
            "--property=MainPID",
            "--property=Transient",
            "--property=FragmentPath",
        ],
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("HermesUI runtime provider provenance could not be queried")

    properties: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            raise RuntimeError("systemd returned malformed HermesUI runtime provider properties")
        key, value = line.split("=", 1)
        if key in properties:
            raise RuntimeError("systemd returned duplicate HermesUI runtime provider properties")
        properties[key] = value
    required = {"MainPID", "Transient", "FragmentPath"}
    if set(properties) != required:
        raise RuntimeError("systemd omitted HermesUI runtime provider properties")
    if properties["MainPID"] != str(pid):
        raise RuntimeError("HermesUI runtime provider MainPID changed after pidfd pinning")
    if properties["Transient"] != "yes":
        raise RuntimeError("HermesUI runtime provider is not the managed transient service")
    expected_fragment = f"/run/user/{os.getuid()}/systemd/transient/{systemd_unit}"
    if properties["FragmentPath"] != expected_fragment:
        raise RuntimeError("HermesUI runtime provider fragment is not the managed transient service")


def stop_owned_process(
    pid: int,
    repo_root: Path,
    home: Path,
    port: int,
    timeout: float,
    verify_only: bool = False,
    systemd_unit: str | None = None,
    systemctl: str | None = None,
) -> None:
    if pid <= 1:
        raise RuntimeError("systemd returned an invalid MainPID")
    pidfd = pidfd_open(pid)
    try:
        verify_owned_process(pid, repo_root, home, port, systemd_unit)
        if (systemd_unit is None) != (systemctl is None):
            raise RuntimeError("systemd unit and systemctl must be supplied together")
        if systemd_unit is not None and systemctl is not None:
            verify_systemd_provider(pid, systemd_unit, systemctl)
        if verify_only:
            return
        try:
            pidfd_send_signal(pidfd, signal.SIGTERM)
        except ProcessLookupError:
            return
        poller = select.poll()
        poller.register(pidfd, select.POLLIN)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("managed HermesUI process did not stop before timeout")
            if poller.poll(max(1, int(remaining * 1000))):
                return
    finally:
        os.close(pidfd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--systemd-unit")
    parser.add_argument("--systemctl")
    args = parser.parse_args()
    try:
        stop_owned_process(
            args.pid,
            args.repo_root,
            args.home,
            args.port,
            args.timeout,
            args.verify_only,
            args.systemd_unit,
            args.systemctl,
        )
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
