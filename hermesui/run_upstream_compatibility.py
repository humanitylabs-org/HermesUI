#!/usr/bin/env python3
"""Run upstream pytest while replacing exact stale frontend assertions.

Every deselected node is documented in a pinned manifest and must have an existing
Hermes UI replacement test. Nothing outside that explicit list is suppressed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "hermesui" / "upstream-frontend-replacements.json"
UPSTREAM = ROOT / "UPSTREAM.json"


def load_replacements() -> list[dict[str, object]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    upstream = json.loads(UPSTREAM.read_text(encoding="utf-8"))
    if manifest.get("schema") != 1:
        raise RuntimeError("unsupported frontend-replacement manifest schema")
    if manifest.get("upstream_commit") != upstream.get("commit"):
        raise RuntimeError("frontend-replacement manifest is not pinned to UPSTREAM.json")
    replacements = manifest.get("replacements")
    if not isinstance(replacements, list) or not replacements:
        raise RuntimeError("frontend-replacement manifest is empty")
    seen: set[str] = set()
    for entry in replacements:
        if not isinstance(entry, dict):
            raise RuntimeError("frontend-replacement entry is not an object")
        nodeid = entry.get("nodeid")
        reason = entry.get("reason")
        covered_by = entry.get("covered_by")
        if not isinstance(nodeid, str) or "::" not in nodeid or nodeid in seen:
            raise RuntimeError(f"invalid or duplicate replacement nodeid: {nodeid!r}")
        if not isinstance(reason, str) or not reason.strip():
            raise RuntimeError(f"missing replacement reason for {nodeid}")
        if not isinstance(covered_by, list) or not covered_by:
            raise RuntimeError(f"missing downstream coverage for {nodeid}")
        upstream_file = ROOT / nodeid.split("::", 1)[0]
        if not upstream_file.is_file():
            raise RuntimeError(f"upstream replacement target does not exist: {nodeid}")
        for replacement in covered_by:
            if not isinstance(replacement, str) or not (ROOT / replacement).is_file():
                raise RuntimeError(
                    f"downstream replacement test does not exist for {nodeid}: {replacement!r}"
                )
        seen.add(nodeid)
    return replacements


def main(argv: list[str]) -> int:
    replacements = load_replacements()
    command = [sys.executable, "-m", "pytest", *argv]
    command.extend(f"--deselect={entry['nodeid']}" for entry in replacements)
    print(
        f"Hermes UI compatibility: replacing {len(replacements)} exact upstream "
        "frontend assertions; all other collected tests remain mandatory.",
        flush=True,
    )
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["tests/"]))
