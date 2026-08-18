#!/usr/bin/env python3
"""Run upstream's lifecycle gate through Hermes UI's Classic view.

The upstream assertions remain byte-for-byte unchanged. This adapter changes only
the initial browser URL so the canonical transcript is visible instead of the
frontend-only dashboard projection.
"""

from __future__ import annotations

from pathlib import Path


UPSTREAM_GATE = Path(__file__).with_name("browser_conversation_lifecycle.py")
NAVIGATION = '        page.goto("/", wait_until="domcontentloaded")'
CLASSIC_NAVIGATION = '''        page.goto("/?session_view=classic", wait_until="domcontentloaded")
        page.wait_for_function(
            "document.documentElement.dataset.sessionView === 'classic'",
            timeout=10000,
        )'''


def adapted_source() -> str:
    source = UPSTREAM_GATE.read_text(encoding="utf-8")
    count = source.count(NAVIGATION)
    if count != 1:
        raise RuntimeError(
            "Upstream lifecycle navigation contract changed: "
            f"expected one default navigation, found {count}"
        )
    return source.replace(NAVIGATION, CLASSIC_NAVIGATION, 1)


def test_adapter_only_selects_the_public_classic_view() -> None:
    source = adapted_source()
    assert source.count("session_view=classic") == 1
    assert source.count("document.documentElement.dataset.sessionView === 'classic'") == 1
    assert source.replace(CLASSIC_NAVIGATION, NAVIGATION, 1) == UPSTREAM_GATE.read_text(
        encoding="utf-8"
    )


def main() -> None:
    namespace = {
        "__name__": "__main__",
        "__file__": str(UPSTREAM_GATE),
        "__package__": None,
    }
    exec(compile(adapted_source(), str(UPSTREAM_GATE), "exec"), namespace)


if __name__ == "__main__":
    main()
