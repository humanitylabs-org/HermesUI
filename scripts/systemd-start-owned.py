#!/usr/bin/env python3
"""Atomically start the managed HermesUI runtime as a transient user service.

systemd's StartTransientUnit operation uses fail-on-name-collision semantics,
so a same-name service appearing at command entry is preserved rather than
restarted or replaced. A separate persistent launcher invokes this helper at
login; the live application remains hermesui.service.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def build_command(
    systemd_run: str,
    unit: str,
    repo_root: Path,
    home: Path,
    port: int,
) -> list[str]:
    if unit != "hermesui.service":
        raise RuntimeError("unexpected HermesUI runtime unit name")
    if not 1024 <= port <= 65535:
        raise RuntimeError("HermesUI requires an unprivileged TCP port")
    repo_root = repo_root.resolve(strict=True)
    home = home.resolve(strict=True)
    bootstrap = (repo_root / "bootstrap.py").resolve(strict=True)
    managed_path = f"{home}/.local/bin:/usr/local/bin:/usr/bin:/bin"
    python = shutil.which("python3", path=managed_path)
    if python is None:
        raise RuntimeError("python3 was not found in the managed launch PATH")
    python = str(Path(python).resolve(strict=True))
    for value in (str(repo_root), str(home), str(bootstrap)):
        if "\n" in value or "\0" in value:
            raise RuntimeError("paths containing newlines or NUL bytes are unsupported")

    return [
        systemd_run,
        "--user",
        "--quiet",
        "--collect",
        f"--unit={unit}",
        "--service-type=exec",
        "--expand-environment=no",
        f"--working-directory={repo_root}",
        "--property=Restart=on-failure",
        "--property=RestartSec=5s",
        "--property=TimeoutStopSec=30s",
        "--setenv=HERMESUI_MANAGED=1",
        f"--setenv=HERMES_WEBUI_PYTHON={python}",
        f"--setenv=HOME={home}",
        f"--setenv=PATH={home}/.local/bin:/usr/local/bin:/usr/bin:/bin",
        "--setenv=HERMES_WEBUI_HOST=127.0.0.1",
        f"--setenv=HERMES_WEBUI_PORT={port}",
        "--setenv=HERMES_WEBUI_PRESERVE_ENV=1",
        "--setenv=HERMES_WEBUI_SECURE=1",
        "--setenv=HERMES_WEBUI_COOKIE_NAME=hermesui_session",
        "--setenv=HERMES_WEBUI_PROFILE_COOKIE_NAME=hermesui_profile",
        "--setenv=HERMES_WEBUI_COOKIE_PATH=/hermesUI",
        python,
        str(bootstrap),
        str(port),
        "--host",
        "127.0.0.1",
        "--no-browser",
        "--foreground",
        "--skip-agent-install",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--systemd-run", default="systemd-run")
    parser.add_argument("--unit", default="hermesui.service")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    try:
        command = build_command(
            args.systemd_run,
            args.unit,
            args.repo_root,
            args.home,
            args.port,
        )
        subprocess.run(command, check=True)
        return 0
    except Exception as exc:
        print(f"ERROR: could not atomically start HermesUI: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
