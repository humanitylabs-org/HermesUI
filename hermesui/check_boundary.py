#!/usr/bin/env python3
"""Enforce Hermes UI's frontend-first fork boundary and explicit narrow extensions."""

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

# Product metadata and deployment code are downstream-owned. Upstream application
# bytes must stay in static/ unless a nonstatic file is listed below with its exact
# post-extension digest and a narrowly documented UI contract.
DOWNSTREAM_EXACT = {
    ".gitignore",
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
PINNED_NONSTATIC_SHA256 = {
    # One catalog row exposes the downstream High Signal summarizer in the
    # existing provider-agnostic Auxiliary Models settings UI. The LLM call
    # itself remains in the Tailnet-only controller and never mutates a session.
    "api/config.py": "1dccfd1400f3f53be0c6ca09cb18f631ce8ca23ea991f5ca12b64091e0d03379",
    # Inherited workflows change only downstream branch reachability and the
    # exact test launchers needed for Hermes UI's replacement frontend contracts.
    ".github/workflows/browser-smoke.yml": "637468a8018ea807e5f8c17128e503faad05ecfcd4bf7e39f62a5f7182560cc6",
    ".github/workflows/conversation-lifecycle.yml": "3cffcd46072429cd509949f1136b67eea0416a52958ab83ef69940338d6a587d",
    ".github/workflows/docker-smoke.yml": "7bc9f0acf11bdb0245678cb7600f7e61aead168ecdad60c6d6d02a98e2c373cc",
    ".github/workflows/docs-ci.yml": "137bbc237ab13f3b6aab1f3f5c59c23706bc81843e152e3cc4dfae4c534163fb",
    ".github/workflows/native-windows-startup.yml": "00d46bdcd5f5a6535d28882ceadeaa07041e94ba1292f43e55268914c4681d4b",
    ".github/workflows/release.yml": "6f83c8e12ad3a6407b4fb18f806bcd3c4c7dc91e544e638c0cda5d6026b7c498",
    ".github/workflows/tests.yml": "002ac5907ca3c6f511dbb7790cd7961eb3a41a7814a96a5542226795c2f3268a",
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
        or path in PINNED_NONSTATIC_SHA256
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

        for path, expected_digest in PINNED_NONSTATIC_SHA256.items():
            if path not in changed:
                continue
            actual_digest = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            if actual_digest != expected_digest:
                raise RuntimeError(f"pinned downstream support digest is stale: {path}")

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
            f"Hermes UI boundary passed: upstream backend {commit} is unchanged except explicit pinned extensions; "
            f"{len(changed_static)} frontend overlay files and "
            f"{len(changed) - len(changed_static)} downstream support files are isolated."
        )
        return 0
    except Exception as exc:
        print(f"Hermes UI boundary failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
