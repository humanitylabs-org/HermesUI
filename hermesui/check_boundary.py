#!/usr/bin/env python3
"""Enforce Hermes UI's frontend-only fork boundary."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANCHOR = ROOT / "UPSTREAM.json"
OVERLAY = ROOT / "hermesui" / "frontend-overlay.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# Product metadata and deployment code are downstream-owned but do not participate
# in the WebUI backend/runtime. All upstream-owned application changes must stay in
# static/ and must be recorded in frontend-overlay.json.
DOWNSTREAM_EXACT = {
    ".github/workflows/hermesui.yml",
    "NOTICE.md",
    "README.md",
    "SECURITY.md",
    "UPSTREAM.json",
    "docs/Tailnet-HermesUI-Prompt.md",
    "docs/UPSTREAM-MAINTENANCE.md",
    "docs/give-this-prompt-to-your-ai.md",
    "qa/tailnet-installer-smoke.sh",
    "qa/update-smoke.sh",
}
DOWNSTREAM_PREFIXES = ("hermesui/",)
DOWNSTREAM_TEST_PREFIXES = (
    "tests/test_hermes_ui_",
    "tests/test_hermesui_subpath_",
)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def allowed_nonstatic(path: str) -> bool:
    return (
        path in DOWNSTREAM_EXACT
        or path.startswith(DOWNSTREAM_PREFIXES)
        or path.startswith(DOWNSTREAM_TEST_PREFIXES)
    )


def main() -> int:
    try:
        anchor = json.loads(ANCHOR.read_text(encoding="utf-8"))
        commit = str(anchor["commit"])
        tree = str(anchor["tree"])
        if anchor.get("repository") != "https://github.com/nesquena/hermes-webui":
            raise RuntimeError("UPSTREAM.json points at an unexpected repository")
        if not SHA_RE.fullmatch(commit) or not SHA_RE.fullmatch(tree):
            raise RuntimeError("UPSTREAM.json must contain full lowercase commit and tree hashes")
        if git("rev-parse", f"{commit}^{{commit}}") != commit:
            raise RuntimeError("the pinned upstream commit is unavailable")
        if git("rev-parse", f"{commit}^{{tree}}") != tree:
            raise RuntimeError("the pinned upstream tree does not match UPSTREAM.json")

        changed = set(filter(None, git("diff", "--name-only", commit, "--").splitlines()))
        changed.update(filter(None, git("ls-files", "--others", "--exclude-standard").splitlines()))
        blocked = sorted(
            path
            for path in changed
            if not path.startswith("static/") and not allowed_nonstatic(path)
        )
        if blocked:
            print("Hermes UI boundary failed; upstream backend/runtime files changed:")
            for path in blocked:
                print(f"- {path}")
            return 1

        manifest = json.loads(OVERLAY.read_text(encoding="utf-8"))
        if manifest.get("schema") != 1 or manifest.get("upstream_commit") != commit:
            raise RuntimeError("frontend-overlay.json is not bound to the pinned upstream commit")
        entries = manifest.get("files")
        if not isinstance(entries, list):
            raise RuntimeError("frontend-overlay.json files must be a list")
        manifest_paths = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise RuntimeError("frontend-overlay.json contains a malformed entry")
            path = entry.get("path")
            if not isinstance(path, str) or not path.startswith("static/") or path in manifest_paths:
                raise RuntimeError("frontend-overlay.json contains an invalid or duplicate path")
            file_path = ROOT / path
            if not file_path.is_file():
                raise RuntimeError(f"overlay file is missing: {path}")
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
            if entry.get("hermesui_sha256") != digest:
                raise RuntimeError(f"overlay digest is stale: {path}")
            upstream = subprocess.run(
                ["git", "show", f"{commit}:{path}"],
                cwd=ROOT,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            upstream_digest = hashlib.sha256(upstream.stdout).hexdigest() if upstream.returncode == 0 else None
            if entry.get("upstream_sha256") != upstream_digest:
                raise RuntimeError(f"overlay upstream digest is stale: {path}")
            manifest_paths.append(path)

        changed_static = sorted(path for path in changed if path.startswith("static/"))
        if sorted(manifest_paths) != changed_static:
            missing = sorted(set(changed_static) - set(manifest_paths))
            extra = sorted(set(manifest_paths) - set(changed_static))
            raise RuntimeError(f"frontend overlay path mismatch; missing={missing}, extra={extra}")

        print(
            f"Hermes UI boundary passed: upstream backend {commit} is untouched; "
            f"{len(changed_static)} frontend overlay files and "
            f"{len(changed) - len(changed_static)} downstream support files are isolated."
        )
        return 0
    except Exception as exc:
        print(f"Hermes UI boundary failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
