import importlib.util
import json
import stat
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "hermesui" / "installer" / "cloudflare_provision.py"
UNITS_PATH = ROOT / "hermesui" / "installer" / "cloudflare_systemd_units.py"


def load_module():
    spec = importlib.util.spec_from_file_location("hermesui_cloudflare_provision", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_units_module():
    spec = importlib.util.spec_from_file_location("hermesui_cloudflare_systemd_units", UNITS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeApi:
    def __init__(self, *, fail_on=None):
        self.fail_on = fail_on
        self.calls = []
        self.apps = []
        self.policies = {}
        self.tunnels = []
        self.configs = {}
        self.records = []
        self.deleted = []

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if self.fail_on == (method, path):
            raise RuntimeError("injected provider failure")
        if path == "/accounts/account/access/organizations" and method == "GET":
            return {"auth_domain": "team.cloudflareaccess.com"}
        if path == "/accounts/account/access/identity_providers?per_page=100" and method == "GET":
            return [{"id": "idp-1", "type": "onetimepin"}]
        if path == "/accounts/account/access/apps?domain=wizard.example.com&per_page=100" and method == "GET":
            return list(self.apps)
        if path == "/accounts/account/access/apps" and method == "POST":
            app = {**body, "id": "app-1", "aud": "aud-1"}
            self.apps.append(app)
            return app
        if path == "/accounts/account/access/apps/app-1/policies" and method == "POST":
            policy = {**body, "id": "policy-1"}
            self.policies.setdefault("app-1", []).append(policy)
            return policy
        if path == "/accounts/account/access/apps/app-1/policies?per_page=100" and method == "GET":
            return list(self.policies.get("app-1", []))
        if path == "/accounts/account/access/apps/app-1" and method == "DELETE":
            self.apps = []
            self.policies = {}
            self.deleted.append("app-1")
            return None
        if path == "/accounts/account/cfd_tunnel?is_deleted=false&name=HermesUI%20wizard.example.com&per_page=100" and method == "GET":
            return list(self.tunnels)
        if path == "/accounts/account/cfd_tunnel" and method == "POST":
            tunnel = {**body, "id": "tunnel-1"}
            self.tunnels.append(tunnel)
            return tunnel
        if path == "/accounts/account/cfd_tunnel/tunnel-1/configurations" and method == "PUT":
            self.configs["tunnel-1"] = body
            return body
        if path == "/accounts/account/cfd_tunnel/tunnel-1/configurations" and method == "GET":
            stored = self.configs.get("tunnel-1", {"config": {"ingress": []}})
            return {
                "account_id": "account",
                "tunnel_id": "tunnel-1",
                "version": 1,
                "config": stored["config"],
            }
        if path == "/accounts/account/cfd_tunnel/tunnel-1/token" and method == "GET":
            return "secret-tunnel-token"
        if path == "/accounts/account/cfd_tunnel/tunnel-1" and method == "DELETE":
            self.tunnels = []
            self.configs.pop("tunnel-1", None)
            self.deleted.append("tunnel-1")
            return None
        if path == "/zones/zone/dns_records?name=wizard.example.com&per_page=100" and method == "GET":
            return list(self.records)
        if path == "/zones/zone/dns_records" and method == "POST":
            record = {**body, "id": "dns-1"}
            self.records.append(record)
            return record
        if path == "/zones/zone/dns_records/dns-1" and method == "DELETE":
            self.records = []
            self.deleted.append("dns-1")
            return None
        raise AssertionError(f"unexpected API call: {method} {path} {body!r}")


def config(module):
    return module.ProvisionConfig(
        account_id="account",
        zone_id="zone",
        hostname="wizard.example.com",
        allowed_emails=("owner@example.com",),
        origin_url="http://127.0.0.1:8793",
        tunnel_name="HermesUI wizard.example.com",
    )


def test_cloudflare_inventory_reader_follows_every_result_page(tmp_path):
    module = load_module()
    token_file = tmp_path / "api.token"
    token_file.write_text("not-a-real-token\n", encoding="utf-8")
    token_file.chmod(0o600)
    api = module.CloudflareApi(token_file, base_url="https://api.invalid")
    seen = []

    def envelope(method, path, body=None):
        seen.append((method, path, body))
        page = 2 if "page=2" in path else 1
        return {
            "success": True,
            "result": [{"id": f"resource-{page}"}],
            "result_info": {"page": page, "total_pages": 2},
        }

    api._request_envelope = envelope
    assert api.list_all("/accounts/account/access/apps?domain=wizard.example.com&per_page=100") == [
        {"id": "resource-1"},
        {"id": "resource-2"},
    ]
    assert [path for _, path, _ in seen] == [
        "/accounts/account/access/apps?domain=wizard.example.com&per_page=100&page=1",
        "/accounts/account/access/apps?domain=wizard.example.com&per_page=100&page=2",
    ]

    seen.clear()

    def tunnel_envelope(method, path, body=None):
        seen.append((method, path, body))
        page = 2 if "page=2" in path else 1
        return {
            "success": True,
            "result": [{"id": f"tunnel-{page}"}],
            "result_info": {"page": page, "per_page": 100, "total_count": 200},
        }

    api._request_envelope = tunnel_envelope
    assert api.list_all("/accounts/account/cfd_tunnel?is_deleted=false&name=HermesUI&per_page=100") == [
        {"id": "tunnel-1"},
        {"id": "tunnel-2"},
    ]
    assert [path for _, path, _ in seen] == [
        "/accounts/account/cfd_tunnel?is_deleted=false&name=HermesUI&per_page=100&page=1",
        "/accounts/account/cfd_tunnel?is_deleted=false&name=HermesUI&per_page=100&page=2",
    ]


def test_cloudflare_provisioning_is_access_first_and_origin_validated(tmp_path):
    module = load_module()
    api = FakeApi()
    token_path = tmp_path / "cloudflared.token"
    state_path = tmp_path / "cloudflare.json"

    state = module.provision(config(module), api, token_path, state_path)

    writes = [(method, path) for method, path, _ in api.calls if method in {"POST", "PUT", "DELETE"}]
    assert writes == [
        ("POST", "/accounts/account/access/apps"),
        ("POST", "/accounts/account/access/apps/app-1/policies"),
        ("POST", "/accounts/account/cfd_tunnel"),
        ("PUT", "/accounts/account/cfd_tunnel/tunnel-1/configurations"),
        ("POST", "/zones/zone/dns_records"),
    ]
    assert api.apps[0]["domain"] == "wizard.example.com"
    assert api.apps[0]["type"] == "self_hosted"
    assert api.apps[0]["allow_iframe"] is True
    assert api.policies["app-1"][0]["include"] == [{"email": {"email": "owner@example.com"}}]
    assert api.configs["tunnel-1"] == {
        "config": {
            "ingress": [
                {
                    "hostname": "wizard.example.com",
                    "service": "http://127.0.0.1:8793",
                    "originRequest": {
                        "access": {"required": True, "teamName": "team", "audTag": ["aud-1"]}
                    },
                },
                {"service": "http_status:404"},
            ],
            "warp-routing": {"enabled": False},
        }
    }
    assert [{key: value for key, value in api.records[0].items() if key != "id"}] == [
        {
            "type": "CNAME",
            "name": "wizard.example.com",
            "content": "tunnel-1.cfargotunnel.com",
            "proxied": True,
            "ttl": 1,
        }
    ]
    assert token_path.read_text(encoding="utf-8") == "secret-tunnel-token\n"
    assert stat.S_IMODE(token_path.stat().st_mode) == 0o600
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved == state
    assert saved["managed"] == {"access_app": True, "dns_record": True, "tunnel": True}
    assert "secret-tunnel-token" not in state_path.read_text(encoding="utf-8")


def test_ambiguous_app_create_response_is_reconciled_without_duplication(tmp_path):
    module = load_module()

    class CommitThenLoseResponse(FakeApi):
        lost = False

        def request(self, method, path, body=None):
            if method == "POST" and path == "/accounts/account/access/apps" and not self.lost:
                self.lost = True
                super().request(method, path, body)
                raise RuntimeError("connection reset after provider commit")
            return super().request(method, path, body)

    api = CommitThenLoseResponse()
    state = module.provision(config(module), api, tmp_path / "connector.token", tmp_path / "state.json")
    assert state["access_app_id"] == "app-1"
    assert len(api.apps) == 1


def test_unreconciled_create_retains_recovery_state_and_cleanup_adopts_exact_resource(tmp_path):
    module = load_module()

    class CommitThenLoseInventory(FakeApi):
        lost = False
        fail_inventory = False

        def request(self, method, path, body=None):
            if method == "POST" and path == "/accounts/account/access/apps" and not self.lost:
                self.lost = True
                self.fail_inventory = True
                super().request(method, path, body)
                raise RuntimeError("connection reset after provider commit")
            if method == "GET" and path == "/accounts/account/access/apps?domain=wizard.example.com&per_page=100" and self.fail_inventory:
                self.fail_inventory = False
                raise RuntimeError("provider inventory temporarily unavailable")
            return super().request(method, path, body)

    api = CommitThenLoseInventory()
    state_path = tmp_path / "state.json"
    token_path = tmp_path / "connector.token"
    with pytest.raises(RuntimeError, match="recovery state was retained"):
        module.provision(config(module), api, token_path, state_path)
    recovery = json.loads(state_path.read_text(encoding="utf-8"))
    assert recovery["status"] == "recovery_required"
    assert recovery["access_app_id"] is None
    assert len(api.apps) == 1

    module.cleanup(config(module), api, token_path, state_path, recovery)
    assert not api.apps
    assert not state_path.exists()


def test_cleanup_continues_after_one_delete_failure_and_is_safe_to_retry(tmp_path):
    module = load_module()

    class ActiveTunnelOnce(FakeApi):
        tunnel_failed = False

        def request(self, method, path, body=None):
            if method == "DELETE" and path == "/accounts/account/cfd_tunnel/tunnel-1" and not self.tunnel_failed:
                self.tunnel_failed = True
                raise RuntimeError("active connections")
            if method == "DELETE" and path.endswith("/dns_records/dns-1") and not self.records:
                raise module.CloudflareApiError("not found", status=404)
            if method == "DELETE" and path.endswith("/access/apps/app-1") and not self.apps:
                raise module.CloudflareApiError("not found", status=404)
            return super().request(method, path, body)

    api = ActiveTunnelOnce()
    state_path = tmp_path / "state.json"
    token_path = tmp_path / "connector.token"
    state = module.provision(config(module), api, token_path, state_path)
    with pytest.raises(RuntimeError, match="tunnel"):
        module.cleanup(config(module), api, token_path, state_path, state)
    assert not api.records
    assert api.tunnels
    assert not api.apps
    assert state_path.exists()

    module.cleanup(config(module), api, token_path, state_path, state)
    assert not api.tunnels
    assert not state_path.exists()


def test_duplicate_hostname_fails_closed_without_mutation(tmp_path):
    module = load_module()
    api = FakeApi()
    api.apps.append({"id": "foreign", "domain": "wizard.example.com", "type": "self_hosted"})

    with pytest.raises(RuntimeError, match="already has an Access application"):
        module.provision(config(module), api, tmp_path / "token", tmp_path / "state")

    assert not [call for call in api.calls if call[0] in {"POST", "PUT", "DELETE"}]


def test_provider_failure_rolls_back_only_resources_created_by_this_run(tmp_path):
    module = load_module()
    api = FakeApi(fail_on=("POST", "/zones/zone/dns_records"))
    token_path = tmp_path / "token"
    state_path = tmp_path / "state.json"

    with pytest.raises(RuntimeError, match="recovery state was retained"):
        module.provision(config(module), api, token_path, state_path)

    assert api.deleted == ["tunnel-1", "app-1"]
    assert api.apps == []
    assert api.tunnels == []
    assert not token_path.exists()
    recovery = json.loads(state_path.read_text(encoding="utf-8"))
    assert recovery["status"] == "recovery_required"

    module.cleanup(config(module), api, token_path, state_path, recovery)
    assert not state_path.exists()


def test_cleanup_requires_matching_owned_state_and_deletes_in_reverse(tmp_path):
    module = load_module()
    api = FakeApi()
    token_path = tmp_path / "token"
    state_path = tmp_path / "state.json"
    state = module.provision(config(module), api, token_path, state_path)

    module.cleanup(config(module), api, token_path, state_path, state)

    assert api.deleted[-3:] == ["dns-1", "tunnel-1", "app-1"]
    assert not token_path.exists()
    assert not state_path.exists()


def test_validation_rejects_unsafe_or_ambiguous_inputs():
    module = load_module()
    with pytest.raises(ValueError, match="hostname"):
        module.ProvisionConfig("account", "zone", "https://wizard.example.com", ("owner@example.com",), "http://127.0.0.1:8793", "name")
    with pytest.raises(ValueError, match="allowed email"):
        module.ProvisionConfig("account", "zone", "wizard.example.com", ("everyone",), "http://127.0.0.1:8793", "name")
    with pytest.raises(ValueError, match="loopback"):
        module.ProvisionConfig("account", "zone", "wizard.example.com", ("owner@example.com",), "http://0.0.0.0:8793", "name")


def test_systemd_units_keep_origin_on_loopback_and_token_out_of_argv(tmp_path):
    module = load_units_module()
    repo = tmp_path / "HermesUI"
    home = tmp_path / "home"
    hermes_home = home / ".hermes"
    token = home / ".config" / "hermesui" / "cloudflared.token"
    cloudflared = tmp_path / "bin" / "cloudflared"
    python = tmp_path / "bin" / "python3"
    for path in (repo, home, hermes_home, token.parent, cloudflared.parent):
        path.mkdir(parents=True, exist_ok=True)
    (repo / "bootstrap.py").write_text("# fixture\n", encoding="utf-8")
    (repo / "hermesui" / "installer").mkdir(parents=True)
    (repo / "hermesui" / "installer" / "runtime-home-guard.py").write_text("# fixture\n", encoding="utf-8")
    token.write_text("not-a-real-token\n", encoding="utf-8")
    cloudflared.write_text("#!/bin/sh\n", encoding="utf-8")
    python.write_text("#!/bin/sh\n", encoding="utf-8")

    app_unit, tunnel_unit = module.render_units(
        repo,
        home,
        hermes_home,
        python,
        cloudflared,
        token,
        8793,
    )

    assert "HERMES_WEBUI_HOST=127.0.0.1" in app_unit
    assert "runtime-home-guard.py" in app_unit
    assert "--token-file" in tunnel_unit
    assert str(token) in tunnel_unit
    assert "not-a-real-token" not in tunnel_unit
    assert "NoNewPrivileges=true" in tunnel_unit
    assert "ProtectSystem=strict" in tunnel_unit


def test_systemd_unit_renderer_rejects_untrusted_executables(tmp_path):
    module = load_units_module()
    with pytest.raises(RuntimeError, match="absolute"):
        module.render_units(tmp_path, tmp_path, tmp_path, Path("python3"), Path("cloudflared"), tmp_path / "token", 8793)


def test_cloudflare_docs_name_every_required_api_token_permission():
    expected = (
        "Cloudflare Tunnel: Edit",
        "Access: Apps and Policies: Edit",
        "Access: Organizations, Identity Providers, and Groups: Read",
        "DNS: Edit",
        "One-Time PIN",
    )
    for relative in ("README.md", "docs/give-this-prompt-to-your-ai.md"):
        content = (ROOT / relative).read_text(encoding="utf-8")
        for permission in expected:
            assert permission in content, f"{relative} omits {permission}"
        assert "recovery state" in content, f"{relative} omits ambiguous-mutation recovery guidance"
