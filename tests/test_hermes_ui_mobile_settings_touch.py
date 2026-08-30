from __future__ import annotations

import contextlib
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
LIVE_ORIGIN = "http://127.0.0.1:8797"


class _CandidateHandler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path) -> None:
        if not path.is_file():
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        body = path.read_bytes().replace(b"__WEBUI_VERSION__", b"mobile-settings-test")
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or path.suffix in {".js", ".json"}:
            content_type += "; charset=utf-8"
        self._send(200, body, content_type)

    def _proxy_live(self) -> None:
        try:
            with urlopen(f"{LIVE_ORIGIN}{self.path}", timeout=15) as response:
                self._send(
                    response.status,
                    response.read(),
                    response.headers.get_content_type(),
                )
        except (OSError, URLError):
            self._send(503, b'{"error":"live backend unavailable"}', "application/json")

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        path = urlsplit(self.path).path
        if path == "/":
            self._serve_file(STATIC / "index.html")
            return
        if path.startswith("/static/"):
            relative = Path(path.removeprefix("/static/"))
            if ".." in relative.parts:
                self._send(400, b"bad path", "text/plain; charset=utf-8")
                return
            self._serve_file(STATIC / relative)
            return
        if path in {"/sw.js", "/manifest.json"}:
            self._serve_file(STATIC / path.removeprefix("/"))
            return
        self._proxy_live()


@contextlib.contextmanager
def _candidate_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CandidateHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_mobile_settings_touch_actions_survive_touchstart_and_open_more_popup():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(
            headless=True,
            executable_path="/usr/bin/google-chrome",
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
        )
        page = context.new_page()
        with _candidate_server() as url:
            page.goto(url, wait_until="domcontentloaded")
            toggle = page.locator("#mobileSessionUtilitiesToggle")
            menu = page.locator("#mobileSessionUtilitiesMenu")
            popup = page.locator("#settingsPopup")
            toggle.wait_for(state="visible")

            assert toggle.inner_text().strip() == "Settings"
            toggle.tap()
            assert menu.is_visible()
            toggle_box = toggle.bounding_box()
            menu_box = menu.bounding_box()
            assert toggle_box and menu_box
            assert menu_box["y"] + menu_box["height"] <= toggle_box["y"]
            for selector in (
                "#mobileSessionViewUtility",
                "#mobileThemeUtility",
                "#mobileMoreUtility",
            ):
                row_box = page.locator(selector).bounding_box()
                assert row_box and row_box["height"] >= 44

            page.evaluate("document.documentElement.dataset.sessionView='classic'")
            page.locator("#mobileSessionViewUtility").tap()
            assert page.locator("html").get_attribute("data-session-view") == "dashboard"
            assert menu.is_visible()

            was_dark = page.locator("html").evaluate("el => el.classList.contains('dark')")
            page.locator("#mobileThemeUtility").tap()
            is_dark = page.locator("html").evaluate("el => el.classList.contains('dark')")
            assert is_dark is not was_dark
            assert menu.is_visible()

            page.locator("#mobileMoreUtility").tap()
            assert not menu.is_visible()
            assert popup.is_visible()

        context.close()
        browser.close()
