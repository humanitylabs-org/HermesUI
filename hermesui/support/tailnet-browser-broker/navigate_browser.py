#!/usr/bin/env python3
"""Navigate the dedicated Tailnet browser without exposing remote debugging."""

from __future__ import annotations

import argparse
import time
from urllib.parse import urlsplit, urlunsplit

from Xlib import X, XK, display
from Xlib.ext import xtest


MAX_URL_LENGTH = 2048
BROWSER_MARKERS = ("chromium", "chrome")
SYMBOL_KEYS = {
    ":": ("semicolon", True),
    "/": ("slash", False),
    ".": ("period", False),
    "-": ("minus", False),
    "_": ("minus", True),
    "?": ("slash", True),
    "&": ("7", True),
    "=": ("equal", False),
    "%": ("5", True),
    "#": ("3", True),
    "+": ("equal", True),
    "~": ("grave", True),
    "@": ("2", True),
    "!": ("1", True),
    "$": ("4", True),
    "(": ("9", True),
    ")": ("0", True),
    ",": ("comma", False),
    ";": ("semicolon", False),
    "*": ("8", True),
    "'": ("apostrophe", False),
    "[": ("bracketleft", False),
    "]": ("bracketright", False),
}


def clean_url(raw: str) -> str:
    if not isinstance(raw, str):
        raise ValueError("URL must be a string")
    value = raw.strip()
    if not value or len(value) > MAX_URL_LENGTH or any(ord(char) < 32 for char in value):
        raise ValueError("URL is invalid")
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("HTTPS is required")
    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not allowed")
    if any(ord(char) > 127 for char in value):
        raise ValueError("URL must be browser-serialized ASCII")
    return urlunsplit(("https", parsed.netloc, parsed.path or "/", parsed.query, parsed.fragment))


def _browser_windows(root):
    matches = []
    stack = [root]
    while stack:
        window = stack.pop()
        try:
            stack.extend(window.query_tree().children)
            attrs = window.get_attributes()
            if attrs.map_state != X.IsViewable:
                continue
            markers = " ".join(window.get_wm_class() or ()).lower()
            if not any(marker in markers for marker in BROWSER_MARKERS):
                continue
            geometry = window.get_geometry()
            area = max(0, geometry.width) * max(0, geometry.height)
            if area:
                matches.append((area, window))
        except Exception:
            continue
    return matches


def _keycode(connection, name: str) -> int:
    keysym = XK.string_to_keysym(name)
    keycode = connection.keysym_to_keycode(keysym)
    if not keycode:
        raise RuntimeError(f"Keyboard key unavailable: {name}")
    return keycode


def _tap(connection, name: str, *, shift: bool = False) -> None:
    shift_code = _keycode(connection, "Shift_L")
    keycode = _keycode(connection, name)
    if shift:
        xtest.fake_input(connection, X.KeyPress, shift_code)
    xtest.fake_input(connection, X.KeyPress, keycode)
    xtest.fake_input(connection, X.KeyRelease, keycode)
    if shift:
        xtest.fake_input(connection, X.KeyRelease, shift_code)


def _type_text(connection, text: str) -> None:
    for char in text:
        if "a" <= char <= "z" or "0" <= char <= "9":
            _tap(connection, char)
        elif "A" <= char <= "Z":
            _tap(connection, char.lower(), shift=True)
        elif char in SYMBOL_KEYS:
            name, shift = SYMBOL_KEYS[char]
            _tap(connection, name, shift=shift)
        else:
            raise ValueError(f"Unsupported URL character: {char!r}")


def navigate(raw_url: str, *, display_name: str | None = None) -> None:
    url = clean_url(raw_url)
    connection = display.Display(display_name)
    try:
        root = connection.screen().root
        windows = _browser_windows(root)
        if not windows:
            raise RuntimeError("Tailnet browser window is unavailable")
        _, window = max(windows, key=lambda item: item[0])
        window.configure(stack_mode=X.Above)
        window.set_input_focus(X.RevertToParent, X.CurrentTime)
        connection.sync()

        control = _keycode(connection, "Control_L")
        xtest.fake_input(connection, X.KeyPress, control)
        _tap(connection, "l")
        xtest.fake_input(connection, X.KeyRelease, control)
        connection.sync()
        time.sleep(0.06)
        _type_text(connection, url)
        _tap(connection, "Return")
        connection.sync()
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--display", default=None)
    args = parser.parse_args()
    navigate(args.url, display_name=args.display)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
