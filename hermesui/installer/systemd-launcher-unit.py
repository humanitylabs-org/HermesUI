#!/usr/bin/env python3
"""Render or verify the exact persistent HermesUI launcher unit."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

MARKER = "# Managed by HermesUI Tailnet installer"


def quoted(value: str) -> str:
    value = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'"{value}"'


def render(
    repo_root: Path,
    home: Path,
    host: str,
    port: int,
    hermes_home: Path | None = None,
    profile: str = "default",
    *,
    legacy: bool = False,
) -> str:
    repo_root = repo_root.resolve(strict=True)
    home = home.resolve(strict=True)
    hermes_home = (hermes_home or (home / ".hermes")).expanduser().resolve(strict=False)
    if host != "127.0.0.1":
        raise RuntimeError("HermesUI launcher must bind to loopback")
    if not 1024 <= port <= 65535:
        raise RuntimeError("HermesUI launcher requires an unprivileged TCP port")
    if profile != "default":
        raise RuntimeError("v0.2.2 standalone installation supports only the default Hermes profile")
    values = (str(repo_root), str(home), str(hermes_home), profile)
    if any("\n" in value or "\0" in value for value in values):
        raise RuntimeError("paths containing newlines or NUL bytes are unsupported")
    starter = repo_root / "hermesui" / "installer" / "systemd-start-owned.py"
    starter.resolve(strict=True)
    if legacy:
        return f'''{MARKER}
[Unit]
Description=HermesUI private Tailnet runtime launcher
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Environment={quoted('HERMESUI_MANAGED=1')}
Environment={quoted('HOME=' + str(home))}
Environment={quoted('PATH=' + str(home) + '/.local/bin:/usr/local/bin:/usr/bin:/bin')}
Environment={quoted('HERMES_WEBUI_HOST=' + host)}
Environment={quoted('HERMES_WEBUI_PORT=' + str(port))}
Environment={quoted('HERMES_WEBUI_PRESERVE_ENV=1')}
Environment={quoted('HERMES_WEBUI_SECURE=1')}
Environment={quoted('HERMES_WEBUI_COOKIE_NAME=hermesui_session')}
Environment={quoted('HERMES_WEBUI_PROFILE_COOKIE_NAME=hermesui_profile')}
ExecStart=/usr/bin/env python3 {quoted(str(starter))} --unit hermesui.service --repo-root {quoted(str(repo_root))} --home {quoted(str(home))} --port {port}

[Install]
WantedBy=default.target
'''
    return f'''{MARKER}
[Unit]
Description=HermesUI private Tailnet standalone runtime launcher
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Environment={quoted('HERMESUI_MANAGED=1')}
Environment={quoted('HERMESUI_MODE=standalone')}
Environment={quoted('HERMESUI_PROFILE=' + profile)}
Environment={quoted('HOME=' + str(home))}
Environment={quoted('HERMES_HOME=' + str(hermes_home))}
Environment={quoted('PATH=' + str(home) + '/.local/bin:/usr/local/bin:/usr/bin:/bin')}
Environment={quoted('HERMES_WEBUI_HOST=' + host)}
Environment={quoted('HERMES_WEBUI_PORT=' + str(port))}
Environment={quoted('HERMES_WEBUI_PRESERVE_ENV=1')}
Environment={quoted('HERMES_WEBUI_SECURE=1')}
Environment={quoted('HERMES_WEBUI_COOKIE_NAME=hermesui_session')}
Environment={quoted('HERMES_WEBUI_PROFILE_COOKIE_NAME=hermesui_profile')}
ExecStart=/usr/bin/env python3 {quoted(str(starter))} --unit hermesui.service --repo-root {quoted(str(repo_root))} --home {quoted(str(home))} --hermes-home {quoted(str(hermes_home))} --profile {quoted(profile)} --port {port}

[Install]
WantedBy=default.target
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("write", "verify"))
    parser.add_argument("path", type=Path)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--hermes-home", type=Path)
    parser.add_argument("--profile", default="default")
    parser.add_argument("--legacy", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    try:
        expected = render(
            args.repo_root,
            args.home,
            args.host,
            args.port,
            args.hermes_home,
            args.profile,
            legacy=args.legacy,
        )
        if args.action == "write":
            args.path.write_text(expected, encoding="utf-8")
            args.path.chmod(0o644)
            return 0
        actual = args.path.read_text(encoding="utf-8")
        if actual != expected:
            raise RuntimeError("launcher unit bytes do not match the managed launch specification")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
