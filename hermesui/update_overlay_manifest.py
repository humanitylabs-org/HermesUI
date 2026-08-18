#!/usr/bin/env python3
"""Regenerate the machine-readable Hermes UI frontend overlay manifest."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANCHOR = ROOT / "UPSTREAM.json"
MANIFEST = ROOT / "hermesui" / "frontend-overlay.json"


def git(*args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
    )
    return result.stdout if binary else result.stdout.strip()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    anchor = json.loads(ANCHOR.read_text(encoding="utf-8"))
    commit = str(anchor["commit"])
    changed = set(filter(None, str(git("diff", "--name-only", commit, "--", "static/")).splitlines()))
    changed.update(
        path
        for path in str(git("ls-files", "--others", "--exclude-standard", "static/")).splitlines()
        if path
    )
    entries = []
    for path in sorted(changed):
        current = (ROOT / path).read_bytes()
        upstream = subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        entries.append(
            {
                "path": path,
                "upstream_sha256": sha256(upstream.stdout) if upstream.returncode == 0 else None,
                "hermesui_sha256": sha256(current),
            }
        )
    payload = {
        "schema": 1,
        "upstream_commit": commit,
        "files": entries,
    }
    MANIFEST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {MANIFEST.relative_to(ROOT)} for {len(entries)} frontend files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
