from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "hermesui" / "support" / "frame-compatibility" / "checker.py"
spec = importlib.util.spec_from_file_location("hermesui_frame_checker", CHECKER_PATH)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def test_clean_url_accepts_only_public_https_shape():
    assert checker.clean_url("https://example.com/path?q=1#fragment") == "https://example.com/path?q=1"
    for value in (
        "http://example.com/",
        "https://user:pass@example.com/",
        "https://example.com:8443/",
        "javascript:alert(1)",
        "",
    ):
        with pytest.raises(checker.CompatibilityError):
            checker.clean_url(value)


def test_resolution_rejects_any_private_or_loopback_answer(monkeypatch):
    monkeypatch.setattr(
        checker.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (checker.socket.AF_INET, checker.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (checker.socket.AF_INET, checker.socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(checker.CompatibilityError, match="private-address"):
        checker.resolve_public_address("example.com")


@pytest.mark.parametrize("unsafe_address", ["224.0.0.1", "ff0e::1"])
def test_resolution_rejects_multicast_answers(monkeypatch, unsafe_address):
    family = checker.socket.AF_INET6 if ":" in unsafe_address else checker.socket.AF_INET
    monkeypatch.setattr(
        checker.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (family, checker.socket.SOCK_STREAM, 6, "", (unsafe_address, 443)),
        ],
    )
    with pytest.raises(checker.CompatibilityError, match="private-address"):
        checker.resolve_public_address("example.com")


def test_request_retries_every_validated_public_address(monkeypatch):
    attempts = []

    class FakeConnection:
        def __init__(self, hostname: str, address: str):
            assert hostname == "example.com"
            self.address = address

        def request(self, *_args, **_kwargs) -> None:
            attempts.append(self.address)
            if self.address == "2001:db8::1":
                raise OSError("unreachable")

        def getresponse(self):
            return FakeResponse(200)

        def close(self) -> None:
            return

    monkeypatch.setattr(
        checker,
        "resolve_public_addresses",
        lambda _hostname: ["2001:db8::1", "93.184.216.34"],
    )
    monkeypatch.setattr(checker, "PinnedHTTPSConnection", FakeConnection)

    response, headers = checker.request_once("https://example.com/path")
    assert response.status == 200
    assert headers == []
    assert attempts == ["2001:db8::1", "93.184.216.34"]


def test_x_frame_options_blocks_cross_origin_but_not_same_origin():
    assert checker.xfo_blocks_parent(["DENY"], "https://example.com")
    assert checker.xfo_blocks_parent(["SAMEORIGIN"], "https://example.com")
    assert not checker.xfo_blocks_parent(["SAMEORIGIN"], checker.PARENT_ORIGIN)
    assert not checker.xfo_blocks_parent([], "https://example.com")


def test_frame_ancestors_is_evaluated_against_exact_hermes_origin():
    assert checker.csp_blocks_parent(["default-src 'self'; frame-ancestors 'none'"], "https://example.com")
    assert checker.csp_blocks_parent(["frame-ancestors 'self'"], "https://example.com")
    assert not checker.csp_blocks_parent(
        [f"default-src 'self'; frame-ancestors {checker.PARENT_ORIGIN}"],
        "https://example.com",
    )
    assert not checker.csp_blocks_parent(
        [f"frame-ancestors {checker.PARENT_ORIGIN}:443"],
        "https://example.com",
    )
    assert not checker.csp_blocks_parent(
        ["frame-ancestors https://*.tail6adf1a.ts.net:443"],
        "https://example.com",
    )
    assert checker.csp_blocks_parent(
        ["frame-ancestors https://*.tail6adf1a.ts.net:8443"],
        "https://example.com",
    )
    assert not checker.csp_blocks_parent(["frame-ancestors https:"], "https://example.com")
    assert not checker.csp_blocks_parent(["default-src 'self'"], "https://example.com")
    assert not checker.csp_blocks_parent(
        ["frame-ancestors-report 'none'; default-src 'self'"],
        "https://example.com",
    )


class FakeResponse:
    def __init__(self, status: int, headers=None):
        self.status = status
        self.fp = None
        self._headers = list(headers or [])

    def getheaders(self):
        return self._headers

    def close(self) -> None:
        return


def test_cloudflare_access_redirect_is_browser_only(monkeypatch):
    def request(url: str):
        assert url == "https://bot.example.com/"
        return FakeResponse(302), [("Location", "https://tenant.cloudflareaccess.com/cdn-cgi/access/login")]

    monkeypatch.setattr(checker, "request_once", request)
    result = checker.evaluate_url("https://bot.example.com/")
    assert result["mode"] == "browser"
    assert result["reason"] == "cloudflare-access"
    assert result["redirects"] == 1


def test_frame_header_decision_is_browser_and_clear_headers_are_inline(monkeypatch):
    monkeypatch.setattr(
        checker,
        "request_once",
        lambda _url: (FakeResponse(200), [("X-Frame-Options", "SAMEORIGIN")]),
    )
    blocked = checker.evaluate_url("https://blocked.example/")
    assert blocked["mode"] == "browser"
    assert blocked["reason"] == "x-frame-options"

    monkeypatch.setattr(
        checker,
        "request_once",
        lambda _url: (FakeResponse(200), [("Content-Type", "text/html")]),
    )
    allowed = checker.evaluate_url("https://allowed.example/")
    assert allowed["mode"] == "inline"
    assert allowed["reason"] == "headers-allow"
