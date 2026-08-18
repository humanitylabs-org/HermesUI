"""Release contract for public shares behind the managed /hermesUI mount."""

from pathlib import Path
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]
SHARE_HTML = (ROOT / "static" / "share.html").read_text(encoding="utf-8")
SHARE_JS = (ROOT / "static" / "share.js").read_text(encoding="utf-8")
BOOT_JS = (ROOT / "static" / "boot.js").read_text(encoding="utf-8")
SESSIONS_JS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")



def test_share_page_constructs_absolute_mounted_assets_before_loading_them() -> None:
    assert "path.lastIndexOf(marker)" in SHARE_HTML
    assert "window.__HERMES_SHARE_APP_ROOT__=root" in SHARE_HTML
    assert "'+root+'static/favicon.svg" in SHARE_HTML
    assert "'+root+'static/style.css" in SHARE_HTML
    assert "'+root+'static/ui.js" in SHARE_HTML
    assert "'+root+'static/share.js" in SHARE_HTML
    assert 'href="#" id="shareHomeLink"' in SHARE_HTML
    assert "document.getElementById('shareHomeLink').href=root" in SHARE_HTML
    assert '<base href=' not in SHARE_HTML
    assert 'href="static/' not in SHARE_HTML
    assert 'src="static/' not in SHARE_HTML
    assert 'href="/static/' not in SHARE_HTML
    assert 'src="/static/' not in SHARE_HTML


def test_share_api_and_generated_links_resolve_inside_mount() -> None:
    mounted_root = "https://device.tailnet.example.ts.net/hermesUI/"
    assert urljoin(mounted_root, "share/token-123") == (
        "https://device.tailnet.example.ts.net/hermesUI/share/token-123"
    )
    assert urljoin(mounted_root, "api/share/token-123") == (
        "https://device.tailnet.example.ts.net/hermesUI/api/share/token-123"
    )
    assert "new URL(`api/share/${encodeURIComponent(token)}`,appRoot)" in SHARE_JS
    assert "new URL(`share/${encodeURIComponent(S.session.share_token)}`,document.baseURI||location.href)" in BOOT_JS
    assert "new URL(`share/${encodeURIComponent(token)}`,document.baseURI||location.href)" in SESSIONS_JS
    assert "res&&res.share&&res.share.share_token" in BOOT_JS
    assert "new URL(`/api/share/" not in SHARE_JS
    assert "new URL(`/share/" not in BOOT_JS
    assert "new URL(`/share/" not in SESSIONS_JS
