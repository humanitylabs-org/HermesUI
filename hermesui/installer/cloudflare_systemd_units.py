#!/usr/bin/env python3
"""Render or verify the exact Cloudflare-mode HermesUI user services."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

APP_MARKER = "# Managed by HermesUI Cloudflare installer: application"
TUNNEL_MARKER = "# Managed by HermesUI Cloudflare installer: connector"


def quoted(value: str) -> str:
    if "\n" in value or "\0" in value:
        raise RuntimeError("systemd values cannot contain newline or NUL bytes")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


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
WorkingDirectory={quoted(str(repo_root))}
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
    parser.add_argument("action", choices=("write", "verify"))
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
            args.app_unit.parent.mkdir(parents=True, exist_ok=True)
            args.app_unit.write_text(app, encoding="utf-8")
            args.app_unit.chmod(0o644)
            args.tunnel_unit.write_text(tunnel, encoding="utf-8")
            args.tunnel_unit.chmod(0o644)
        else:
            if args.app_unit.read_text(encoding="utf-8") != app:
                raise RuntimeError("HermesUI application unit differs from the managed specification")
            if args.tunnel_unit.read_text(encoding="utf-8") != tunnel:
                raise RuntimeError("cloudflared unit differs from the managed specification")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
