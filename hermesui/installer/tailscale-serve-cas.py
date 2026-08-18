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
    if "Web" not in config:
        handlers: dict[str, Any] = {}
    else:
        web = config["Web"]
        if not isinstance(web, dict):
            raise RuntimeError("Serve Web configuration is invalid; no mutation performed")
        if listener not in web:
            handlers = {}
        else:
            server = web[listener]
            if not isinstance(server, dict):
                raise RuntimeError("Serve listener configuration is invalid; no mutation performed")
            if "Handlers" not in server:
                handlers = {}
            else:
                raw_handlers = server["Handlers"]
                if not isinstance(raw_handlers, dict):
                    raise RuntimeError("Serve Handlers configuration is invalid; no mutation performed")
                handlers = raw_handlers
    present = path in handlers
    top = handlers.get(path)
    if present and (not isinstance(top, dict) or set(top) != {"Proxy"}):
        raise RuntimeError(
            f"Serve path {path} has a non-Proxy handler; no mutation performed"
        )
    value = top.get("Proxy") if isinstance(top, dict) else None

    def foreground_has_route(current: dict[str, Any]) -> bool:
        if "Foreground" not in current:
            return False
        foreground = current["Foreground"]
        if not isinstance(foreground, dict):
            raise RuntimeError("Serve Foreground configuration is invalid; no mutation performed")
        for nested in foreground.values():
            if not isinstance(nested, dict):
                raise RuntimeError("Serve Foreground entry is invalid; no mutation performed")
            if "Web" in nested:
                nested_web = nested["Web"]
                if not isinstance(nested_web, dict):
                    raise RuntimeError("Serve Foreground Web configuration is invalid; no mutation performed")
                if listener in nested_web:
                    nested_server = nested_web[listener]
                    if not isinstance(nested_server, dict):
                        raise RuntimeError("Serve Foreground listener configuration is invalid; no mutation performed")
                    if "Handlers" in nested_server:
                        nested_handlers = nested_server["Handlers"]
                        if not isinstance(nested_handlers, dict):
                            raise RuntimeError("Serve Foreground Handlers configuration is invalid; no mutation performed")
                        if path in nested_handlers:
                            return True
            if foreground_has_route(nested):
                return True
        return False

    return normalize_proxy(value), foreground_has_route(config), present


def normalize_proxy(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).rstrip("/")


def assert_no_funnel(value: Any) -> None:
    """Reject any enabled or ambiguous Funnel setting in the GET snapshot."""
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "AllowFunnel":
                if isinstance(nested, bool):
                    if nested:
                        raise RuntimeError("Tailscale Funnel is enabled; no mutation performed")
                elif isinstance(nested, dict):
                    if any(not isinstance(entry, bool) for entry in nested.values()):
                        raise RuntimeError("Tailscale AllowFunnel configuration is invalid; no mutation performed")
                    if any(nested.values()):
                        raise RuntimeError("Tailscale Funnel is enabled; no mutation performed")
                elif nested is not None:
                    raise RuntimeError("Tailscale AllowFunnel configuration is invalid; no mutation performed")
            assert_no_funnel(nested)
    elif isinstance(value, list):
        for nested in value:
            assert_no_funnel(nested)


def apply_route(
    config: dict[str, Any],
    listener: str,
    path: str,
    desired: str | None,
    remove_tcp_if_owned: bool,
) -> None:
    if "Web" not in config:
        web = {}
        config["Web"] = web
    else:
        web = config["Web"]
    if not isinstance(web, dict):
        raise RuntimeError("Serve Web configuration is invalid; no mutation performed")
    if desired is not None:
        if "TCP" not in config:
            tcp = {}
            config["TCP"] = tcp
        else:
            tcp = config["TCP"]
        if not isinstance(tcp, dict):
            raise RuntimeError("Serve TCP configuration is invalid; no mutation performed")
        if "443" in tcp and tcp["443"] != {"HTTPS": True}:
            current_tcp = tcp["443"]
            raise RuntimeError(f"TCP 443 has incompatible Serve configuration: {current_tcp!r}")
        tcp["443"] = {"HTTPS": True}
        if listener not in web:
            server = {}
            web[listener] = server
        else:
            server = web[listener]
            if not isinstance(server, dict):
                raise RuntimeError("Serve listener configuration is invalid; no mutation performed")
        if "Handlers" not in server:
            handlers = {}
            server["Handlers"] = handlers
        else:
            handlers = server["Handlers"]
            if not isinstance(handlers, dict):
                raise RuntimeError("Serve Handlers configuration is invalid; no mutation performed")
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
        if not isinstance(config, dict):
            raise RuntimeError("Serve configuration is invalid; no mutation performed")
        current, foreground_match, present = route_values(config, args.listener, args.path)
        if foreground_match:
            raise RuntimeError("foreground Serve ownership is ambiguous; no mutation performed")
        if present and current is None:
            raise RuntimeError("Serve route handler is invalid; no mutation performed")
        if current != expected:
            raise RuntimeError(
                f"Serve route changed ownership: expected {expected!r}, found {current!r}; no mutation performed"
            )
        if desired is not None:
            assert_no_funnel(config)
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
