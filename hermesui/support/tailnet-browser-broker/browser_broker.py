#!/usr/bin/env python3
"""Serve the Wizard OS frame bridge and navigate its Tailnet browser."""

from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from navigate_browser import clean_url, navigate


MAX_BODY_BYTES = 4096
MIN_NAVIGATION_INTERVAL = 0.4
ALLOWED_FILES = {
    "/tailnet-frame/": "tailnet-frame/index.html",
    "/tailnet-frame/index.html": "tailnet-frame/index.html",
    "/tailnet-frame/apps.json": "tailnet-frame/apps.json",
}


class FrameServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, *, root: Path, display_name: str):
        super().__init__(address, handler)
        self.root = root.resolve()
        self.display_name = display_name
        self.navigation_lock = threading.Lock()
        self.last_navigation = 0.0


class FrameHandler(BaseHTTPRequestHandler):
    def _send_headers(self, status: HTTPStatus, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "frame-src https:; connect-src 'self'; img-src 'self' data:; frame-ancestors 'self'",
        )
        self.end_headers()

    def _json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._send_headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _same_origin(self) -> bool:
        host = (self.headers.get("Host") or "").strip()
        origin = (self.headers.get("Origin") or "").strip()
        return bool(host) and origin == f"https://{host}"

    def do_GET(self) -> None:
        server = cast(FrameServer, self.server)
        path = urlsplit(self.path).path
        if path == "/tailnet-frame":
            self.send_response(HTTPStatus.PERMANENT_REDIRECT)
            self.send_header("Location", "/tailnet-frame/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        relative = ALLOWED_FILES.get(path)
        if not relative:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        candidate = (server.root / relative).resolve()
        if server.root not in candidate.parents or not candidate.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/json":
            content_type += "; charset=utf-8"
        self._send_headers(HTTPStatus.OK, content_type, len(body))
        self.wfile.write(body)

    def do_POST(self) -> None:
        server = cast(FrameServer, self.server)
        if urlsplit(self.path).path != "/tailnet-frame/navigate":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if not self._same_origin():
            self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            return
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "JSON required"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "invalid request size"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
            raw_url = payload.get("url", "") if isinstance(payload, dict) else ""
            url = clean_url(raw_url if isinstance(raw_url, str) else "")
        except (json.JSONDecodeError, ValueError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid destination"})
            return

        try:
            with server.navigation_lock:
                delay = MIN_NAVIGATION_INTERVAL - (time.monotonic() - server.last_navigation)
                if delay > 0:
                    time.sleep(delay)
                navigate(url, display_name=server.display_name)
                server.last_navigation = time.monotonic()
        except Exception:
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "browser unavailable"})
            return
        self._json(HTTPStatus.OK, {"ok": True})

    def log_message(self, format: str, *args) -> None:
        # The destination stays in the JSON body, never in request or service logs.
        super().log_message(format, *args)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8807)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--display", default=":99")
    args = parser.parse_args()
    server = FrameServer((args.host, args.port), FrameHandler, root=args.root, display_name=args.display)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
