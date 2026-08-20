#!/usr/bin/env python3
"""Tailnet-only framing compatibility checker for HermesUI bookmarks."""

from __future__ import annotations

import ipaddress
import json
import socket
import ssl
import time
from http.client import HTTPResponse, HTTPSConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import parse_qs, urljoin, urlsplit

BIND = "127.0.0.1"
PORT = 8809
PARENT_ORIGIN = "https://oscarvps.tail6adf1a.ts.net"
MAX_REDIRECTS = 6
MAX_QUERY_LENGTH = 4096
CACHE_TTL_SECONDS = 300
USER_AGENT = "HermesUI-Frame-Compatibility/1.0"
REDIRECT_CODES = {301, 302, 303, 307, 308}

_cache: dict[str, tuple[float, dict[str, object]]] = {}
_cache_lock = Lock()


class CompatibilityError(Exception):
    """Expected request validation or network failure."""


class PinnedHTTPSConnection(HTTPSConnection):
    def __init__(self, hostname: str, address: str, timeout: float = 8.0):
        self._tls_context = ssl.create_default_context()
        super().__init__(hostname, port=443, timeout=timeout, context=self._tls_context)
        self._address = address

    def connect(self) -> None:
        raw = socket.create_connection((self._address, 443), self.timeout)
        self.sock = self._tls_context.wrap_socket(raw, server_hostname=self.host)


def clean_url(raw: str) -> str:
    if not isinstance(raw, str) or not raw or len(raw) > MAX_QUERY_LENGTH:
        raise CompatibilityError("invalid-url")
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise CompatibilityError("invalid-url") from exc
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise CompatibilityError("invalid-url")
    try:
        port = parsed.port
    except ValueError as exc:
        raise CompatibilityError("invalid-port") from exc
    if port not in (None, 443):
        raise CompatibilityError("unsupported-port")
    if parsed.fragment:
        parsed = parsed._replace(fragment="")
    return parsed.geturl()


def resolve_public_addresses(hostname: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise CompatibilityError("dns-failed") from exc
    addresses: list[str] = []
    for info in infos:
        address = str(info[4][0])
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise CompatibilityError("dns-failed")
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise CompatibilityError("dns-failed") from exc
        if (
            not parsed.is_global
            or parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_multicast
            or parsed.is_reserved
            or parsed.is_unspecified
        ):
            raise CompatibilityError("private-address")
    return addresses


def resolve_public_address(hostname: str) -> str:
    """Return the first safe address for compatibility with existing callers."""
    return resolve_public_addresses(hostname)[0]


def request_once(url: str) -> tuple[HTTPResponse, list[tuple[str, str]]]:
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    addresses = resolve_public_addresses(hostname)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    last_error: OSError | ssl.SSLError | None = None
    for address in addresses:
        connection = PinnedHTTPSConnection(hostname, address)
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "Host": hostname,
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            headers = response.getheaders()
            return response, headers
        except (OSError, ssl.SSLError) as exc:
            last_error = exc
            connection.close()
    raise CompatibilityError("network-failed") from last_error


def origin_for(url: str) -> str:
    parsed = urlsplit(url)
    port = parsed.port
    suffix = f":{port}" if port and port != 443 else ""
    return f"https://{parsed.hostname}{suffix}"


def host_source_allows_parent(source: str, document_origin: str) -> bool:
    parent = urlsplit(PARENT_ORIGIN)
    document = urlsplit(document_origin)
    if "://" in source:
        source_scheme, remainder = source.split("://", 1)
    else:
        source_scheme, remainder = document.scheme.lower(), source
    if source_scheme != parent.scheme.lower():
        return False
    try:
        parsed_source = urlsplit(f"{source_scheme}://{remainder}")
        if (
            parsed_source.username
            or parsed_source.password
            or parsed_source.query
            or parsed_source.fragment
            or parsed_source.path not in ("", "/")
        ):
            return False
        source_host = (parsed_source.hostname or "").lower()
        parent_host = (parent.hostname or "").lower()
        if not source_host or not parent_host:
            return False
        port_wildcard = parsed_source.netloc.endswith(":*")
        if port_wildcard:
            source_port = parent.port or 443
        else:
            source_port = parsed_source.port or 443
        parent_port = parent.port or 443
    except (TypeError, ValueError):
        return False
    if source_port != parent_port:
        return False
    if source_host == "*":
        return True
    if source_host.startswith("*."):
        allowed_host = source_host[2:]
        return bool(allowed_host) and parent_host.endswith("." + allowed_host)
    if "*" in source_host:
        return False
    return source_host == parent_host


def source_allows_parent(source: str, document_origin: str) -> bool:
    token = source.strip()
    lowered = token.lower()
    if lowered == "*":
        return True
    if lowered == "'none'":
        return False
    if lowered == "'self'":
        return PARENT_ORIGIN == document_origin
    if lowered == "https:":
        return True
    if lowered.startswith("http:"):
        return False
    return host_source_allows_parent(lowered, document_origin)


def csp_blocks_parent(values: list[str], document_origin: str) -> bool:
    for value in values:
        directives = [part.strip() for part in value.split(";")]
        ancestor = next(
            (
                part
                for part in directives
                if part.split(None, 1) and part.split(None, 1)[0].lower() == "frame-ancestors"
            ),
            None,
        )
        if ancestor is None:
            continue
        sources = ancestor.split()[1:]
        if not sources or not any(source_allows_parent(source, document_origin) for source in sources):
            return True
    return False


def xfo_blocks_parent(values: list[str], document_origin: str) -> bool:
    for value in values:
        for token in value.replace(",", " ").split():
            directive = token.strip().upper()
            if directive == "DENY":
                return True
            if directive == "SAMEORIGIN" and document_origin != PARENT_ORIGIN:
                return True
    return False


def evaluate_url(raw_url: str) -> dict[str, object]:
    initial = clean_url(raw_url)
    current = initial
    hops = 0
    while True:
        parsed = urlsplit(current)
        if (parsed.hostname or "").lower().endswith(".cloudflareaccess.com"):
            return {"mode": "browser", "reason": "cloudflare-access", "checkedUrl": current, "redirects": hops}
        response, headers = request_once(current)
        try:
            status = int(response.status)
            locations = [value for name, value in headers if name.lower() == "location"]
            if status in REDIRECT_CODES and locations:
                if hops >= MAX_REDIRECTS:
                    raise CompatibilityError("too-many-redirects")
                current = clean_url(urljoin(current, locations[-1]))
                hops += 1
                continue
            document_origin = origin_for(current)
            xfo_values = [value for name, value in headers if name.lower() == "x-frame-options"]
            csp_values = [value for name, value in headers if name.lower() == "content-security-policy"]
            if xfo_blocks_parent(xfo_values, document_origin):
                return {"mode": "browser", "reason": "x-frame-options", "checkedUrl": current, "redirects": hops}
            if csp_blocks_parent(csp_values, document_origin):
                return {"mode": "browser", "reason": "frame-ancestors", "checkedUrl": current, "redirects": hops}
            return {"mode": "inline", "reason": "headers-allow", "checkedUrl": current, "redirects": hops}
        finally:
            response.close()
            try:
                response.fp.close() if response.fp else None
            except Exception:
                pass


def cached_evaluate(url: str) -> dict[str, object]:
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(url)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return dict(cached[1])
    result = evaluate_url(url)
    with _cache_lock:
        if len(_cache) >= 256:
            oldest = min(_cache, key=lambda key: _cache[key][0])
            _cache.pop(oldest, None)
        _cache[url] = (now, dict(result))
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "HermesUIFrameCheck/1"

    def log_message(self, format: str, *args: object) -> None:
        del format, args
        return

    def send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/health":
            self.send_json(200, {"ok": True})
            return
        if parsed.path not in ("/", "/frame-check", "/frame-check/"):
            self.send_json(404, {"ok": False, "error": "not-found"})
            return
        query = parse_qs(parsed.query, keep_blank_values=True)
        values = query.get("url", [])
        if len(values) != 1:
            self.send_json(400, {"ok": False, "error": "url-required"})
            return
        try:
            result = cached_evaluate(values[0])
        except CompatibilityError as exc:
            self.send_json(200, {"ok": True, "mode": "unknown", "reason": str(exc)})
            return
        except Exception:
            self.send_json(200, {"ok": True, "mode": "unknown", "reason": "check-failed"})
            return
        self.send_json(200, {"ok": True, **result})


if __name__ == "__main__":
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
