#!/usr/bin/env python3
"""CAS-update one Tailscale Serve route through LocalAPI.

The LocalAPI ETag is sent as If-Match, so a route/configuration change after the
GET cannot be overwritten. The expected handler is also checked before the
write, closing the preflight-to-command race in the higher-level installer.
"""

from __future__ import annotations

import argparse
import http.client
import json
import socket
import sys
from typing import Any


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str):
        super().__init__("local-tailscaled.sock")
        self.socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_path)


def request(socket_path: str, method: str, body: bytes | None = None, headers: dict[str, str] | None = None):
    conn = UnixHTTPConnection(socket_path)
    try:
        conn.request(method, "/localapi/v0/serve-config", body=body, headers=headers or {})
        response = conn.getresponse()
        payload = response.read()
        return response.status, dict(response.getheaders()), payload
    finally:
        conn.close()


def route_values(config: dict[str, Any], listener: str, path: str) -> tuple[str | None, bool, bool]:
    web = config.get("Web")
    if web is None:
        handlers: dict[str, Any] = {}
    elif not isinstance(web, dict):
        raise RuntimeError("Serve Web configuration is invalid; no mutation performed")
    else:
        server = web.get(listener)
        if server is None:
            handlers = {}
        elif not isinstance(server, dict):
            raise RuntimeError("Serve listener configuration is invalid; no mutation performed")
        else:
            raw_handlers = server.get("Handlers")
            if raw_handlers is None:
                handlers = {}
            elif not isinstance(raw_handlers, dict):
                raise RuntimeError("Serve Handlers configuration is invalid; no mutation performed")
            else:
                handlers = raw_handlers
    present = path in handlers
    top = handlers.get(path)
    if present and (not isinstance(top, dict) or set(top) != {"Proxy"}):
        raise RuntimeError(
            f"Serve path {path} has a non-Proxy handler; no mutation performed"
        )
    value = top.get("Proxy") if isinstance(top, dict) else None

    def foreground_has_route(current: dict[str, Any]) -> bool:
        foreground = current.get("Foreground") or {}
        if not isinstance(foreground, dict):
            return False
        for nested in foreground.values():
            if not isinstance(nested, dict):
                continue
            nested_web = nested.get("Web")
            nested_server = nested_web.get(listener) if isinstance(nested_web, dict) else None
            nested_handlers = nested_server.get("Handlers") if isinstance(nested_server, dict) else None
            if (isinstance(nested_handlers, dict) and path in nested_handlers) or foreground_has_route(nested):
                return True
        return False

    return normalize_proxy(value), foreground_has_route(config), present


def normalize_proxy(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).rstrip("/")


def apply_route(
    config: dict[str, Any],
    listener: str,
    path: str,
    desired: str | None,
    remove_tcp_if_owned: bool,
) -> None:
    web = config.setdefault("Web", {})
    if desired is not None:
        tcp = config.setdefault("TCP", {})
        current_tcp = tcp.get("443")
        if current_tcp is not None and current_tcp != {"HTTPS": True}:
            raise RuntimeError(f"TCP 443 has incompatible Serve configuration: {current_tcp!r}")
        tcp["443"] = {"HTTPS": True}
        server = web.setdefault(listener, {})
        handlers = server.setdefault("Handlers", {})
        handlers[path] = {"Proxy": desired}
        return

    server = web.get(listener)
    if not isinstance(server, dict):
        return
    handlers = server.get("Handlers")
    if not isinstance(handlers, dict):
        return
    handlers.pop(path, None)
    if not handlers:
        web.pop(listener, None)
    if not web:
        config.pop("Web", None)
    if remove_tcp_if_owned and not any(str(key).endswith(":443") for key in web):
        tcp = config.get("TCP")
        if isinstance(tcp, dict) and tcp.get("443") == {"HTTPS": True}:
            tcp.pop("443", None)
            if not tcp:
                config.pop("TCP", None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", default="/var/run/tailscale/tailscaled.sock")
    parser.add_argument("--listener", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--expected", required=True, help="expected proxy URL or 'absent'")
    parser.add_argument("--desired", required=True, help="desired proxy URL or 'absent'")
    parser.add_argument("--remove-tcp-if-owned", action="store_true")
    args = parser.parse_args()

    expected = None if args.expected == "absent" else normalize_proxy(args.expected)
    desired = None if args.desired == "absent" else normalize_proxy(args.desired)
    try:
        status, headers, payload = request(args.socket, "GET")
        if status != 200:
            raise RuntimeError(f"LocalAPI GET failed with HTTP {status}: {payload.decode(errors='replace')}")
        etag = next((value for key, value in headers.items() if key.lower() == "etag"), "")
        if not etag:
            raise RuntimeError("LocalAPI did not provide a Serve configuration ETag")
        config = json.loads(payload or b"null") or {}
        current, foreground_match, present = route_values(config, args.listener, args.path)
        if foreground_match:
            raise RuntimeError("foreground Serve ownership is ambiguous; no mutation performed")
        if present and current is None:
            raise RuntimeError("Serve route handler is invalid; no mutation performed")
        if current != expected:
            raise RuntimeError(
                f"Serve route changed ownership: expected {expected!r}, found {current!r}; no mutation performed"
            )
        apply_route(config, args.listener, args.path, desired, args.remove_tcp_if_owned)
        body = json.dumps(config, separators=(",", ":"), sort_keys=True).encode()
        status, _, payload = request(
            args.socket,
            "POST",
            body=body,
            headers={"Content-Type": "application/json", "If-Match": etag},
        )
        if status != 200:
            raise RuntimeError(
                f"LocalAPI CAS rejected Serve update with HTTP {status}: {payload.decode(errors='replace')}"
            )
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
