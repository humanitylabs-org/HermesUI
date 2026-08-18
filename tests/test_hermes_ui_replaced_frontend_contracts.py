from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


class _ManifestHandler:
    def __init__(self):
        self.status = None
        self.sent_headers: list[tuple[str, str]] = []
        self.body = bytearray()
        self.wfile = self

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent_headers.append((name, value))

    def end_headers(self):
        pass

    def write(self, data):
        self.body.extend(data)

    def header(self, name):
        return next(
            (value for key, value in self.sent_headers if key.lower() == name.lower()),
            None,
        )


def _manifest_response(path: str) -> tuple[_ManifestHandler, dict]:
    from api.routes import handle_get

    handler = _ManifestHandler()
    handle_get(handler, urlparse(f"http://example.com{path}"))
    return handler, json.loads(bytes(handler.body).decode("utf-8"))


def test_help_pane_keeps_docs_and_retargets_issues_to_hermesui():
    start = INDEX.index('<div class="settings-pane" id="settingsPaneHelp">')
    end = INDEX.index('</div>\n      </div>\n    </div>\n  </main>', start)
    pane = INDEX[start:end]

    assert 'href="https://get-hermes.ai/"' in pane
    assert 'href="https://github.com/humanitylabs-org/HermesUI/issues"' in pane
    assert 'href="https://github.com/nesquena/hermes-webui/issues"' not in pane
    assert pane.count('target="_blank"') == 2
    assert pane.count('rel="noopener noreferrer"') == 2


def test_phone_shell_intentionally_hides_the_reload_control():
    phone_start = CSS.index("@media(max-width:640px)")
    phone_css = CSS[phone_start:]
    assert (
        ".app-titlebar-inner,.app-titlebar-spacer,.app-titlebar-reload{display:none!important;}"
        in phone_css
    )
    assert (
        '.mobile-session-tabs{display:block;flex:1 1 auto;min-width:0;height:46px;'
        in phone_css
    )


def test_hermesui_manifest_routes_are_branded_parseable_and_installable():
    for path in (
        "/manifest.json",
        "/manifest.webmanifest",
        "/session/manifest.json",
        "/session/manifest.webmanifest",
    ):
        handler, manifest = _manifest_response(path)
        assert handler.status == 200, path
        assert (handler.header("Content-Type") or "").startswith(
            "application/manifest+json"
        ), path
        assert manifest["name"] == "HermesUI", path
        assert manifest["short_name"] == "HermesUI", path
        icons = manifest.get("icons", [])
        assert any("512" in icon.get("sizes", "") for icon in icons), path
        for icon in icons:
            src = icon.get("src", "")
            if src.startswith("http"):
                continue
            assert (ROOT / src.lstrip("./")).is_file(), (path, src)
