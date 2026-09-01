#!/usr/bin/env python3
"""Render or verify the exact Cloudflare-mode HermesUI user services."""

from __future__ import annotations

import argparse
import os
import secrets
import stat
import sys
from pathlib import Path

APP_MARKER = "# Managed by HermesUI Cloudflare installer: application"
TUNNEL_MARKER = "# Managed by HermesUI Cloudflare installer: connector"


def quoted(value: str) -> str:
    if "\n" in value or "\0" in value:
        raise RuntimeError("systemd values cannot contain newline or NUL bytes")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


def systemd_path(value: str) -> str:
    """Encode one absolute filesystem path for a non-shell systemd directive."""
    if not value.startswith("/"):
        raise RuntimeError("systemd path must be absolute")
    encoded: list[str] = []
    safe = b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/._-+@,:"
    for byte in value.encode("utf-8"):
        if byte in safe:
            encoded.append(chr(byte))
        elif byte == ord("%"):
            encoded.append("%%")
        else:
            encoded.append(f"\\x{byte:02x}")
    return "".join(encoded)


def _read_regular(path: Path) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError(f"refusing non-regular managed unit: {path}")
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks), info
    finally:
        os.close(fd)


def _publish_new(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    parent_fd = os.open(path.parent, directory_flags)
    temporary = f".{path.name}.hermesui-{os.getpid()}-{secrets.token_hex(8)}"
    file_fd = -1
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        file_fd = os.open(temporary, flags, 0o644, dir_fd=parent_fd)
        payload = content.encode("utf-8")
        written = 0
        while written < len(payload):
            written += os.write(file_fd, payload[written:])
        os.fsync(file_fd)
        os.link(
            temporary,
            path.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
            follow_symlinks=False,
        )
        destination = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        source = os.fstat(file_fd)
        if (destination.st_dev, destination.st_ino) != (source.st_dev, source.st_ino):
            raise RuntimeError(f"managed unit publication identity mismatch: {path}")
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        try:
            os.unlink(temporary, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)


def _verify_exact(path: Path, expected: str) -> None:
    actual, _ = _read_regular(path)
    if actual != expected.encode("utf-8"):
        raise RuntimeError(f"managed unit differs from the specification: {path}")


def _remove_exact(path: Path, expected: str) -> None:
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    parent_fd = os.open(path.parent, directory_flags)
    quarantine = f".{path.name}.hermesui-remove-{os.getpid()}-{secrets.token_hex(8)}"
    moved = False
    try:
        os.rename(path.name, quarantine, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        moved = True
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        file_fd = os.open(quarantine, flags, dir_fd=parent_fd)
        try:
            info = os.fstat(file_fd)
            if not stat.S_ISREG(info.st_mode):
                raise RuntimeError(f"refusing non-regular managed unit: {path}")
            chunks = []
            while True:
                chunk = os.read(file_fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            if b"".join(chunks) != expected.encode("utf-8"):
                raise RuntimeError(f"managed unit differs from the specification: {path}")
        except Exception:
            try:
                os.link(
                    quarantine,
                    path.name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
                os.unlink(quarantine, dir_fd=parent_fd)
                moved = False
            except FileExistsError:
                pass
            raise
        finally:
            os.close(file_fd)
        os.unlink(quarantine, dir_fd=parent_fd)
        moved = False
    finally:
        if moved:
            print(f"ERROR: managed unit was quarantined at {path.parent / quarantine}", file=sys.stderr)
        os.close(parent_fd)


def absolute_existing(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise RuntimeError(f"{label} must be an absolute path")
    try:
        return path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"{label} does not exist") from exc


def render_units(
    repo_root: Path,
    home: Path,
    hermes_home: Path,
    python: Path,
    cloudflared: Path,
    token_file: Path,
    port: int,
) -> tuple[str, str]:
    repo_root = absolute_existing(repo_root, "repository")
    home = absolute_existing(home, "home")
    hermes_home = absolute_existing(hermes_home, "Hermes home")
    python = absolute_existing(python, "Python executable")
    cloudflared = absolute_existing(cloudflared, "cloudflared executable")
    token_file = absolute_existing(token_file, "connector token file")
    if not 1024 <= port <= 65535:
        raise RuntimeError("HermesUI requires an unprivileged TCP port")
    guard = absolute_existing(repo_root / "hermesui" / "installer" / "runtime-home-guard.py", "runtime guard")
    values = tuple(map(str, (repo_root, home, hermes_home, python, cloudflared, token_file, guard)))
    if any("\n" in value or "\0" in value for value in values):
        raise RuntimeError("paths containing newline or NUL bytes are unsupported")

    app = f'''{APP_MARKER}
[Unit]
Description=Wizard App (HermesUI) private runtime
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
WorkingDirectory={systemd_path(str(repo_root))}
Environment={quoted('HERMESUI_MANAGED=1')}
Environment={quoted('HERMESUI_MODE=standalone')}
Environment={quoted('HERMESUI_ACCESS_MODE=cloudflare')}
Environment={quoted('HERMESUI_PROFILE=default')}
Environment={quoted('HOME=' + str(home))}
Environment={quoted('HERMES_HOME=' + str(hermes_home))}
Environment={quoted('PATH=' + str(home) + '/.local/bin:/usr/local/bin:/usr/bin:/bin')}
Environment={quoted('HERMES_WEBUI_HOST=127.0.0.1')}
Environment={quoted('HERMES_WEBUI_PORT=' + str(port))}
Environment={quoted('HERMES_WEBUI_PRESERVE_ENV=1')}
Environment={quoted('HERMES_WEBUI_SECURE=1')}
Environment={quoted('HERMES_WEBUI_COOKIE_NAME=wizardapp_session')}
Environment={quoted('HERMES_WEBUI_PROFILE_COOKIE_NAME=wizardapp_profile')}
ExecStart={quoted(str(python))} {quoted(str(guard))} exec --repo-root {quoted(str(repo_root))} --python {quoted(str(python))} --hermes-home {quoted(str(hermes_home))} --profile default --port {port}
Restart=on-failure
RestartSec=5s
TimeoutStopSec=30s
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true

[Install]
WantedBy=default.target
'''

    tunnel = f'''{TUNNEL_MARKER}
[Unit]
Description=Wizard App Cloudflare Tunnel connector
After=network-online.target hermesui.service
Wants=network-online.target hermesui.service

[Service]
Type=simple
ExecStart={quoted(str(cloudflared))} tunnel --no-autoupdate --loglevel info --transport-loglevel warn run --token-file {quoted(str(token_file))}
Restart=on-failure
RestartSec=5s
TimeoutStopSec=30s
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=read-only
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictRealtime=true

[Install]
WantedBy=default.target
'''
    return app, tunnel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("write", "verify", "remove"))
    parser.add_argument("--app-unit", type=Path, required=True)
    parser.add_argument("--tunnel-unit", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--hermes-home", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--cloudflared", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    try:
        app, tunnel = render_units(
            args.repo_root,
            args.home,
            args.hermes_home,
            args.python,
            args.cloudflared,
            args.token_file,
            args.port,
        )
        if args.action == "write":
            _publish_new(args.app_unit, app)
            try:
                _publish_new(args.tunnel_unit, tunnel)
            except Exception:
                _remove_exact(args.app_unit, app)
                raise
        elif args.action == "verify":
            _verify_exact(args.app_unit, app)
            _verify_exact(args.tunnel_unit, tunnel)
        else:
            _verify_exact(args.app_unit, app)
            _verify_exact(args.tunnel_unit, tunnel)
            _remove_exact(args.tunnel_unit, tunnel)
            _remove_exact(args.app_unit, app)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
