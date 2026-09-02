#!/usr/bin/env python3
"""Fail closed before starting a second Hermes execution backend.

This helper is the transient service entrypoint. It scans same-UID Linux
processes immediately before every initial start and systemd restart, then
execs the reviewed WebUI bootstrap only when no other likely Hermes/WebUI
execution process uses the same resolved HERMES_HOME.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

PROFILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def normalize_home(value: str | Path) -> Path:
    raw = str(value)
    if not raw or "\n" in raw or "\0" in raw:
        raise RuntimeError("HERMES_HOME must be a non-empty safe path")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise RuntimeError("HERMES_HOME must be absolute")
    return path.resolve(strict=False)


def _read_nul(path: Path) -> list[str]:
    data = path.read_bytes()
    return [item.decode("utf-8", errors="surrogateescape") for item in data.split(b"\0") if item]


def _environment(pid_dir: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in _read_nul(pid_dir / "environ"):
        key, separator, value = item.partition("=")
        if separator != "=" or not key or key in values:
            raise RuntimeError("process environment is malformed or ambiguous")
        values[key] = value
    return values


def _webui_tree(script: str, cwd: Path | None = None) -> bool:
    try:
        path = Path(script)
        if not path.is_absolute() and cwd is not None:
            path = cwd / path
        path = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    if path.name not in {"server.py", "bootstrap.py"}:
        return False
    root = path.parent
    return (root / "api" / "routes.py").is_file() and (root / "static" / "index.html").is_file()


def _webui_cwd(cwd: Path | None) -> bool:
    return bool(
        cwd is not None
        and (cwd / "server.py").is_file()
        and (cwd / "api" / "routes.py").is_file()
        and (cwd / "static" / "index.html").is_file()
    )


def _process_owns_listener(pid_dir: Path, raw_port: str) -> bool:
    if not raw_port.isdigit() or not 1 <= int(raw_port) <= 65535:
        return False
    sockets: set[str] = set()
    try:
        for fd in (pid_dir / "fd").iterdir():
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            match = re.fullmatch(r"socket:\[(\d+)\]", target)
            if match:
                sockets.add(match.group(1))
    except OSError:
        return False
    if not sockets:
        return False
    expected_port = f"{int(raw_port):04X}"
    for table in (pid_dir / "net" / "tcp", pid_dir / "net" / "tcp6"):
        try:
            lines = table.read_text(encoding="ascii").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10 or fields[3] != "0A":
                continue
            local_port = fields[1].rsplit(":", 1)[-1].upper()
            if local_port == expected_port and fields[9] in sockets:
                return True
    return False


def likely_execution_process(
    argv: list[str],
    env: dict[str, str],
    *,
    cwd: Path | None = None,
    owns_listener: bool = False,
) -> bool:
    if any(_webui_tree(arg, cwd) for arg in argv[:3]):
        return True
    command = " ".join(argv).lower()
    if "-m" in argv and "server" in argv and _webui_cwd(cwd):
        return True
    if re.search(r"(?:^|[/ ])hermes(?:\s+|$).*(?:serve|api-server|gateway)", command):
        return True
    if owns_listener and (env.get("HERMES_WEBUI_PORT") or env.get("HERMESUI_MANAGED") == "1"):
        return "python" in command or "server" in command or "hermes" in command
    return False


def process_hermes_home(env: dict[str, str]) -> Path:
    configured = env.get("HERMES_HOME", "").strip()
    if configured:
        return normalize_home(configured)
    home = env.get("HOME", "").strip()
    if not home:
        raise RuntimeError("likely execution process has no readable HOME or HERMES_HOME")
    return normalize_home(Path(home) / ".hermes")


def conflicting_processes(
    target_home: Path,
    *,
    proc_root: Path = Path("/proc"),
    allow_pids: frozenset[int] = frozenset(),
) -> list[tuple[int, str]]:
    target_home = normalize_home(target_home)
    uid = os.getuid()
    conflicts: list[tuple[int, str]] = []
    try:
        entries = list(proc_root.iterdir())
    except OSError as exc:
        raise RuntimeError(f"cannot inspect Linux process state: {exc}") from exc
    for pid_dir in entries:
        if (
            not pid_dir.name.isdigit()
            or int(pid_dir.name) == os.getpid()
            or int(pid_dir.name) in allow_pids
        ):
            continue
        try:
            if pid_dir.stat().st_uid != uid:
                continue
            argv = _read_nul(pid_dir / "cmdline")
            if not argv:
                continue
            try:
                cwd = (pid_dir / "cwd").resolve(strict=True)
            except (OSError, RuntimeError):
                cwd = None
            try:
                env = _environment(pid_dir)
            except (OSError, RuntimeError) as exc:
                if likely_execution_process(argv, {}, cwd=cwd):
                    raise RuntimeError(
                        f"cannot establish runtime-home ownership for likely execution process PID {pid_dir.name}: {exc}"
                    ) from exc
                continue
            owns_listener = _process_owns_listener(pid_dir, env.get("HERMES_WEBUI_PORT", ""))
            if not likely_execution_process(argv, env, cwd=cwd, owns_listener=owns_listener):
                continue
            try:
                home = process_hermes_home(env)
            except RuntimeError as exc:
                raise RuntimeError(
                    f"cannot establish runtime-home ownership for likely execution process PID {pid_dir.name}: {exc}"
                ) from exc
            if home == target_home:
                conflicts.append((int(pid_dir.name), " ".join(argv[:3])))
        except FileNotFoundError:
            continue
        except PermissionError as exc:
            raise RuntimeError(f"cannot inspect same-UID process PID {pid_dir.name}: {exc}") from exc
    return sorted(conflicts)


def guard(
    target_home: Path,
    *,
    proc_root: Path = Path("/proc"),
    allow_pids: frozenset[int] = frozenset(),
) -> None:
    conflicts = conflicting_processes(target_home, proc_root=proc_root, allow_pids=allow_pids)
    if conflicts:
        pids = ", ".join(str(pid) for pid, _ in conflicts)
        raise RuntimeError(
            "refusing to start a second Hermes/WebUI execution backend over "
            f"{normalize_home(target_home)}; conflicting same-user process PID(s): {pids}. "
            "Do not choose another port. Keep the existing runtime and wait for a compatible client-only HermesUI release."
        )


def exec_runtime(args: argparse.Namespace) -> None:
    repo_root = args.repo_root.resolve(strict=True)
    bootstrap = (repo_root / "bootstrap.py").resolve(strict=True)
    python = args.python.resolve(strict=True)
    hermes_home = normalize_home(args.hermes_home)
    if args.profile != "default" or not PROFILE_RE.fullmatch(args.profile):
        raise RuntimeError("Wizard App supports only the default Hermes profile for standalone installation")
    guard(hermes_home)
    env = os.environ.copy()
    env["HERMES_HOME"] = str(hermes_home)
    env["HERMESUI_MODE"] = "standalone"
    env["HERMESUI_PROFILE"] = args.profile
    argv = [
        str(python),
        str(bootstrap),
        str(args.port),
        "--host",
        "127.0.0.1",
        "--no-browser",
        "--foreground",
        "--skip-agent-install",
    ]
    os.execve(str(python), argv, env)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    normalize = subparsers.add_parser("normalize")
    normalize.add_argument("path")
    check = subparsers.add_parser("check")
    check.add_argument("--hermes-home", type=Path, required=True)
    check.add_argument("--allow-pid", type=int, action="append", default=[])
    execute = subparsers.add_parser("exec")
    execute.add_argument("--repo-root", type=Path, required=True)
    execute.add_argument("--python", type=Path, required=True)
    execute.add_argument("--hermes-home", type=Path, required=True)
    execute.add_argument("--profile", default="default")
    execute.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    try:
        if args.action == "normalize":
            print(normalize_home(args.path))
        elif args.action == "check":
            if any(pid <= 1 for pid in args.allow_pid):
                raise RuntimeError("allowed runtime PIDs must be greater than one")
            guard(args.hermes_home, allow_pids=frozenset(args.allow_pid))
            print(f"OK: no conflicting execution backend uses {normalize_home(args.hermes_home)}")
        else:
            if not 1024 <= args.port <= 65535:
                raise RuntimeError("HermesUI requires an unprivileged TCP port")
            exec_runtime(args)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
