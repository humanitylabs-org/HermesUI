"""Regression tests for password login behind the /hermesUI mount."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LOGIN_JS = ROOT / "static" / "login.js"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is required for login.js contract tests")
def test_login_redirect_stays_inside_browser_visible_mount() -> None:
    assert NODE is not None
    cases = {
        "https://device.tailnet.example.ts.net/login": "./",
        "https://device.tailnet.example.ts.net/login?next=/": "/",
        "https://device.tailnet.example.ts.net/login?next=/session/abc%3Ftab%3Dx": "/session/abc?tab=x",
        "https://device.tailnet.example.ts.net/hermesUI/login": "/hermesUI/",
        "https://device.tailnet.example.ts.net/hermesUI/login?next=/": "/hermesUI/",
        "https://device.tailnet.example.ts.net/hermesUI/login?next=/session/abc%3Ftab%3Dx": "/hermesUI/session/abc?tab=x",
        "https://device.tailnet.example.ts.net/hermesUI/login?next=/hermesUI/session/abc": "/hermesUI/session/abc",
        "https://device.tailnet.example.ts.net/hermesUI/login?next=//evil.example/path": "/hermesUI/",
        "https://device.tailnet.example.ts.net/hermesUI/login?next=/session/login%3Fnext%3D/": "/hermesUI/",
    }
    program = f"""
const fs = require('fs');
const vm = require('vm');
global.document = {{ addEventListener: function () {{}} }};
vm.runInThisContext(fs.readFileSync({json.dumps(str(LOGIN_JS))}, 'utf8'), {{ filename: 'static/login.js' }});
const cases = {json.dumps(cases)};
const results = {{}};
for (const [href, expected] of Object.entries(cases)) {{
  results[href] = _safeLoginNextPath(href);
}}
process.stdout.write(JSON.stringify(results));
"""
    completed = subprocess.run(
        [NODE, "-e", program],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout) == cases
