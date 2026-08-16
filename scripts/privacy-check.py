#!/usr/bin/env python3
"""Fail when tracked public-package files contain private data or live credentials."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {"", ".css", ".html", ".ini", ".js", ".json", ".md", ".py", ".sh", ".svg", ".toml", ".txt", ".xml", ".yml", ".yaml"}
PATTERNS = {
    "private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "common API token": re.compile(r"\b(?:sk-|xox[baprs]-)[A-Za-z0-9_-]{20,}\b"),
    "bearer token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}", re.IGNORECASE),
    "private Tailnet hostname": re.compile(r"https?://(?!<this-device>|device\.tailnet\.example)[A-Za-z0-9-]+\.[A-Za-z0-9-]+\.ts\.net", re.IGNORECASE),
}


def tracked_files() -> list[Path]:
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, stdout=subprocess.PIPE)
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


def main() -> int:
    extra_terms = [term.strip() for term in os.environ.get("HERMESUI_PRIVATE_DENYLIST", "").split(",") if term.strip()]
    findings: list[str] = []
    checker = Path(__file__).resolve()
    for path in tracked_files():
        rel = path.relative_to(ROOT)
        path_text = rel.as_posix()
        is_checker = path.resolve() == checker
        folded_path = path_text.casefold()
        for term in extra_terms:
            if term.casefold() in folded_path:
                findings.append(f"{rel}: private denylist term in filename")
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        patterns = PATTERNS if not path_text.startswith("tests/") else {
            "private Tailnet hostname": PATTERNS["private Tailnet hostname"],
        }
        # The checker necessarily contains its built-in labels and regex source,
        # but externally supplied private terms must still scan this file.
        if is_checker:
            patterns = {}
        for label, pattern in patterns.items():
            if pattern.search(text):
                findings.append(f"{rel}: {label}")
        folded = text.casefold()
        for term in extra_terms:
            if term.casefold() in folded:
                findings.append(f"{rel}: private denylist term")
    if findings:
        print("Privacy check failed:")
        for finding in sorted(set(findings)):
            print(f"- {finding}")
        return 1
    print("Privacy check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
