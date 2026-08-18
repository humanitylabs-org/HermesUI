#!/usr/bin/env python3
"""Run mandatory upstream pytest with explicit downstream reconciliation.

Exact stale frontend assertions are replaced by documented Hermes UI coverage.
Separately documented order-sensitive upstream nodes remain mandatory but run in
fresh subprocesses so unrelated frontend test boundaries cannot mask or trigger
their process-global state leaks.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "hermesui" / "upstream-frontend-replacements.json"
ISOLATED_MANIFEST = ROOT / "hermesui" / "upstream-isolated-tests.json"
UPSTREAM = ROOT / "UPSTREAM.json"


def _load_manifest(path: Path, key: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    upstream = json.loads(UPSTREAM.read_text(encoding="utf-8"))
    if manifest.get("schema") != 1:
        raise RuntimeError(f"unsupported {path.name} schema")
    if manifest.get("upstream_commit") != upstream.get("commit"):
        raise RuntimeError(f"{path.name} is not pinned to UPSTREAM.json")
    entries = manifest.get(key)
    if not isinstance(entries, list) or not entries:
        raise RuntimeError(f"{path.name} is empty")
    return manifest, entries


def load_replacements() -> list[dict[str, object]]:
    _, replacements = _load_manifest(MANIFEST, "replacements")
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


def load_isolated_tests() -> list[dict[str, object]]:
    _, isolated = _load_manifest(ISOLATED_MANIFEST, "isolated_tests")
    replacement_nodeids = {entry["nodeid"] for entry in load_replacements()}
    seen: set[str] = set()
    for entry in isolated:
        if not isinstance(entry, dict):
            raise RuntimeError("isolated-test entry is not an object")
        nodeid = entry.get("nodeid")
        reason = entry.get("reason")
        if not isinstance(nodeid, str) or "::" not in nodeid or nodeid in seen:
            raise RuntimeError(f"invalid or duplicate isolated nodeid: {nodeid!r}")
        if nodeid in replacement_nodeids:
            raise RuntimeError(f"isolated node is also a frontend replacement: {nodeid}")
        if not isinstance(reason, str) or not reason.strip():
            raise RuntimeError(f"missing isolation reason for {nodeid}")
        if not (ROOT / nodeid.split("::", 1)[0]).is_file():
            raise RuntimeError(f"isolated upstream test does not exist: {nodeid}")
        seen.add(nodeid)
    return isolated


def _shard_id(argv: list[str]) -> int | None:
    for index, arg in enumerate(argv):
        if arg.startswith("--shard-id="):
            return int(arg.split("=", 1)[1])
        if arg == "--shard-id" and index + 1 < len(argv):
            return int(argv[index + 1])
    return None


def _run_isolated_tests(isolated: list[dict[str, object]], argv: list[str]) -> int:
    shard_id = _shard_id(argv)
    if shard_id not in (None, 0):
        return 0
    result = 0
    for entry in isolated:
        nodeid = str(entry["nodeid"])
        print(f"Hermes UI compatibility: running order-sensitive upstream node fresh: {nodeid}", flush=True)
        code = subprocess.call(
            [sys.executable, "-m", "pytest", nodeid, "-q", "-p", "no:cacheprovider"],
            cwd=ROOT,
        )
        if code and not result:
            result = code
    return result


def main(argv: list[str]) -> int:
    replacements = load_replacements()
    isolated = load_isolated_tests()
    command = [sys.executable, "-m", "pytest", *argv]
    command.extend(f"--deselect={entry['nodeid']}" for entry in replacements)
    command.extend(f"--deselect={entry['nodeid']}" for entry in isolated)
    print(
        f"Hermes UI compatibility: replacing {len(replacements)} exact upstream "
        f"frontend assertions and isolating {len(isolated)} mandatory order-sensitive node(s); "
        "all other collected tests remain mandatory.",
        flush=True,
    )
    shared_result = subprocess.call(command, cwd=ROOT)
    isolated_result = _run_isolated_tests(isolated, argv)
    return shared_result or isolated_result


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["tests/"]))
