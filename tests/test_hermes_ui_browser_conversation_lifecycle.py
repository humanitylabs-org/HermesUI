#!/usr/bin/env python3
"""Run upstream's lifecycle gate through Hermes UI's Classic view.

The upstream lifecycle assertions remain byte-for-byte unchanged. This adapter
selects the canonical transcript, mocks deployment-provided optional app APIs,
and filters only Chromium's exact benign report-only frame warning.
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
ERROR_CAPTURE = '''        text = message.text
        if not any(needle in text.lower() for needle in benign):
            errors.append(("console", text))'''
FILTERED_ERROR_CAPTURE = '''        text = message.text
        if (
            not _is_benign_report_only_frame_ancestors_warning(text)
            and not any(needle in text.lower() for needle in benign)
        ):
            errors.append(("console", text))'''
APP_ROUTE_SETUP = '        errors = _capture_page_errors(page)'
APP_ROUTE_SETUP_WITH_MOCKS = '''        wizard_canvas = {"revision": 0, "scene": None}

        def _route_optional_app_api(route):
            request_path = urlsplit(route.request.url).path
            request_method = route.request.method
            if request_path == "/apps/api/private-apps" and request_method == "GET":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"apps": []}),
                )
                return
            if request_path != "/apps/api/wizard-canvas":
                route.fallback()
                return
            if request_method == "GET":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(wizard_canvas),
                )
                return
            if request_method == "PUT":
                payload = json.loads(_safe_request_post_data(route.request) or "{}")
                if payload.get("baseRevision") != wizard_canvas["revision"]:
                    route.fulfill(
                        status=409,
                        content_type="application/json",
                        body=json.dumps({
                            "error": "revision conflict",
                            "revision": wizard_canvas["revision"],
                        }),
                    )
                    return
                wizard_canvas["revision"] += 1
                wizard_canvas["scene"] = payload.get("scene")
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"revision": wizard_canvas["revision"]}),
                )
                return
            route.fallback()

        page.route("**/apps/api/private-apps", _route_optional_app_api)
        page.route("**/apps/api/wizard-canvas", _route_optional_app_api)
        errors = _capture_page_errors(page)'''
REPORT_ONLY_FRAME_ANCESTORS_PREFIX = "Framing 'http://127.0.0.1:"
REPORT_ONLY_FRAME_ANCESTORS_SUFFIX = (
    "/' violates the following report-only Content Security Policy directive: "
    '"frame-ancestors \'none\'". The violation has been logged, but no further action '
    "has been taken."
)


def _is_benign_report_only_frame_ancestors_warning(text: str) -> bool:
    normalized = text[:-1] if text.endswith("\n") else text
    if not (
        normalized.startswith(REPORT_ONLY_FRAME_ANCESTORS_PREFIX)
        and normalized.endswith(REPORT_ONLY_FRAME_ANCESTORS_SUFFIX)
    ):
        return False
    port = normalized[
        len(REPORT_ONLY_FRAME_ANCESTORS_PREFIX) : -len(REPORT_ONLY_FRAME_ANCESTORS_SUFFIX)
    ]
    return port.isdigit()


def _replace_once(source: str, original: str, replacement: str, contract: str) -> str:
    count = source.count(original)
    if count != 1:
        raise RuntimeError(
            f"Upstream lifecycle {contract} contract changed: "
            f"expected one match, found {count}"
        )
    return source.replace(original, replacement, 1)


def adapted_source() -> str:
    source = UPSTREAM_GATE.read_text(encoding="utf-8")
    source = _replace_once(source, NAVIGATION, CLASSIC_NAVIGATION, "navigation")
    source = _replace_once(source, ERROR_CAPTURE, FILTERED_ERROR_CAPTURE, "console error")
    return _replace_once(source, APP_ROUTE_SETUP, APP_ROUTE_SETUP_WITH_MOCKS, "app route")


def test_adapter_preserves_upstream_lifecycle_assertions() -> None:
    source = adapted_source()
    assert source.count("session_view=classic") == 1
    assert source.count("document.documentElement.dataset.sessionView === 'classic'") == 1
    assert source.count('page.route("**/apps/api/wizard-canvas"') == 1
    assert source.count('page.route("**/apps/api/private-apps"') == 1
    restored = source.replace(CLASSIC_NAVIGATION, NAVIGATION, 1)
    restored = restored.replace(FILTERED_ERROR_CAPTURE, ERROR_CAPTURE, 1)
    restored = restored.replace(APP_ROUTE_SETUP_WITH_MOCKS, APP_ROUTE_SETUP, 1)
    assert restored == UPSTREAM_GATE.read_text(encoding="utf-8")


def test_console_filter_is_limited_to_the_exact_report_only_frame_warning() -> None:
    warning = (
        REPORT_ONLY_FRAME_ANCESTORS_PREFIX
        + "43117"
        + REPORT_ONLY_FRAME_ANCESTORS_SUFFIX
        + "\n"
    )
    assert _is_benign_report_only_frame_ancestors_warning(warning)
    assert _is_benign_report_only_frame_ancestors_warning(warning.removesuffix("\n"))
    assert not _is_benign_report_only_frame_ancestors_warning(
        "Failed to load resource: the server responded with a status of 404 (Not Found)"
    )
    assert not _is_benign_report_only_frame_ancestors_warning(
        warning.replace("report-only ", "")
    )
    assert not _is_benign_report_only_frame_ancestors_warning(
        warning.replace("frame-ancestors 'none'", "frame-ancestors 'self'")
    )


def main() -> None:
    namespace = {
        "__name__": "__main__",
        "__file__": str(UPSTREAM_GATE),
        "__package__": None,
        "_is_benign_report_only_frame_ancestors_warning": (
            _is_benign_report_only_frame_ancestors_warning
        ),
    }
    exec(compile(adapted_source(), str(UPSTREAM_GATE), "exec"), namespace)


if __name__ == "__main__":
    main()
