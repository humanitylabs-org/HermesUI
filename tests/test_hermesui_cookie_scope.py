"""Release contract for cookies on the managed /hermesUI Tailnet mount."""

from __future__ import annotations

from api import auth
from api.helpers import build_profile_cookie, clear_profile_cookie


class _Handler:
    request = object()
    headers: dict[str, str] = {}

    def __init__(self) -> None:
        self.set_cookies: list[str] = []

    def send_header(self, key: str, value: str) -> None:
        if key == "Set-Cookie":
            self.set_cookies.append(value)


def _assert_managed_attributes(header: str, name: str) -> None:
    assert header.startswith(f"{name}=")
    assert "Path=/hermesUI" in header
    assert "Secure" in header
    assert "HttpOnly" in header
    assert "SameSite=Lax" in header


def test_managed_session_cookie_set_and_clear_are_mount_scoped(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_WEBUI_COOKIE_NAME", "hermesui_session")
    monkeypatch.setenv("HERMES_WEBUI_COOKIE_PATH", "/hermesUI")
    monkeypatch.setenv("HERMES_WEBUI_SECURE", "1")
    handler = _Handler()

    auth.set_auth_cookie(handler, "token.signature")
    auth.clear_auth_cookie(handler)

    assert len(handler.set_cookies) == 2
    for header in handler.set_cookies:
        _assert_managed_attributes(header, "hermesui_session")
    assert "Max-Age=0" in handler.set_cookies[1]


def test_managed_profile_cookie_set_and_clear_are_mount_scoped(monkeypatch) -> None:
    monkeypatch.setattr(auth, "is_auth_enabled", lambda: False)
    monkeypatch.setenv("HERMES_WEBUI_PROFILE_COOKIE_NAME", "hermesui_profile")
    monkeypatch.setenv("HERMES_WEBUI_COOKIE_PATH", "/hermesUI")
    monkeypatch.setenv("HERMES_WEBUI_SECURE", "1")
    handler = _Handler()

    handler.set_cookies.append(build_profile_cookie("default", handler))
    clear_profile_cookie(handler)

    assert len(handler.set_cookies) == 2
    for header in handler.set_cookies:
        _assert_managed_attributes(header, "hermesui_profile")
    assert "Max-Age=0" in handler.set_cookies[1]
