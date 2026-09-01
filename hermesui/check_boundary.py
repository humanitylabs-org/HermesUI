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
    # Native WebUI archive now performs a versioned cold-storage transition.
    # The exact owned contract is documented in
    # hermesui/session-cold-archive-contract.md and covered by the downstream
    # test_hermes_ui_true_cold_archive.py suite. Imported channel memory keeps
    # upstream metadata-only behavior.
    "api/models.py": "2d33916801f7fe876436c90d3cd9154b4fb6f91c82c14f84603eead2e54d5185",
    "api/routes.py": "1d82f6b685000c9f0e5d58599eb447597da33d7638fbaeecdc9e96366902bc37",
    "api/session_cold_archive.py": "ec5b3a0b0e6332d9d18f0fb649db34a66cd1b06a19df52717ffea1713c0f559f",
    "api/upload.py": "9d4eff0a1f15b3606f076baffa9ff8eba024bdd54cfe4a11a3c9e5480d4ec854",
    # Two inherited lifecycle regressions now assert the cold-archive cache
    # eviction and fail-closed deletion semantics rather than metadata-only
    # archive behavior.
    "tests/test_issue2057_worktree_lifecycle.py": "30e1188a32889b2010f90ef5f7a0ed1508fc41dbdd25dcc6068be469f3681df7",
    "tests/test_metadata_save_wipe_1558.py": "6040d7d5b6dc2bd2d1056a78f4d6d0e24b8527834c05619c38aa7d8bb5a3494e",
    # Existing save and static-route regressions are narrowed to the stronger
    # per-session storage serialization and the longer cold-aware handlers.
    "tests/test_issue765_streaming_persistence.py": "16db2fdb08dc176984a202360e1a9859d507a5eb986b453a947d57eb7ba0676e",
    "tests/test_issue2057_worktree_ui_static.py": "ca03980b60b22d515999a26941850cb5fa5841842352fbb5afd3f98ff9837e5a",
    "tests/test_regressions.py": "d8866c66644a59f81a80c47aca1e881b3635ac8b613425ab3201bee121d0f622",
    # These inherited regression tests are intentionally carried by the
    # current hotfix release line and are byte-pinned rather than broadly
    # opening the upstream test namespace.
    "tests/test_compact_voice_note_rendering.py": "530ccfba0091c47e363551d62109a145e039ac67078c1d73f1d59d1a46a02f2d",
    "tests/test_stale_stream_cleanup.py": "63efe65c93e1c855c9f9ac484811e2d3c46e6b4378687a736b44fceae4ed2005",
    "tests/test_svg_audio_video_rendering.py": "d86f6ad7086c791d7239708eb7a320b826c5298e9cdde804a59d907919bcc84d",
    # These inherited transcript regressions now pin the downstream calm-thread
    # contract: redundant assistant identity and per-response jump chrome stay
    # absent while TPS, Transparent Stream, DOM recycling, and settled ordering
    # retain their existing behavior.
    "tests/test_issue1617_tps_message_header.py": "fa80752bd2212bb1f038d8750868e78532a0aa23c40935f698520204ab03876e",
    "tests/test_issue2246_question_jump.py": "2fe1c188ec8ca4061e23f90ba2576e43fa1153ea1ed7f3f2c448e41eeb12a0d0",
    "tests/test_issue3820_chat_activity_display_mode.py": "9280699a73e049b44db42e7aedb2e78daf0c257f7ec9316a42014aca3b9627e8",
    "tests/test_issue4346_vscroll_footer_jitter.py": "d1493dcffbdc2536b14b7d90ad6a6f76598ad099d7aa1ae02fa4bc7716fb2a1a",
    "tests/test_issue4793_dom_recycle_hardening.py": "f25da120c33440d2786611bfdad448a8a9d1d0377de02ca8fd345feef9109ec2",
    "tests/test_live_to_final_anchor_visible_order.py": "662d795f0f72caffd99aa12ec8e4884fedb8031a1e9af64a24798bf0f357e237",
    # The restart-guard regression belongs to the already-carried Wizard App
    # lifecycle hotfix on this release line.
    "tests/test_wizard_app_systemd_restart_guard.py": "9813977b86cd4d8c93d16c6b6deba6c1803686a3bdacd44ee3dca16d24d707d1",
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
                print(
                    "Hermes UI boundary failed; upstream backend/runtime file has "
                    f"a stale pinned digest: {path}"
                )
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
            f"Hermes UI boundary passed: upstream backend {commit} is untouched except explicit pinned extensions; "
            f"{len(changed_static)} frontend overlay files and "
            f"{len(changed) - len(changed_static)} downstream support files are isolated."
        )
        return 0
    except Exception as exc:
        print(f"Hermes UI boundary failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
