import importlib.util
import json
import re
import shutil
import stat
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

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
        if path == "/accounts/account/access/apps/app-1" and method == "GET":
            if not self.apps:
                raise load_module().CloudflareApiError("not found", status=404)
            return dict(self.apps[0])
        if path == "/accounts/account/access/apps/app-1" and method == "DELETE":
            self.apps = []
            self.policies = {}
            self.deleted.append("app-1")
            return None
        if path.startswith("/accounts/account/cfd_tunnel?") and method == "GET":
            name = parse_qs(urlsplit(path).query).get("name", [""])[0]
            return [item for item in self.tunnels if item.get("name") == name]
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
        if path == "/accounts/account/cfd_tunnel/tunnel-1" and method == "GET":
            if not self.tunnels:
                raise load_module().CloudflareApiError("not found", status=404)
            return dict(self.tunnels[0])
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
        if path == "/zones/zone/dns_records/dns-1" and method == "GET":
            if not self.records:
                raise load_module().CloudflareApiError("not found", status=404)
            return dict(self.records[0])
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


def test_explicit_unsuccessful_2xx_is_definitive_while_5xx_remains_ambiguous(tmp_path, monkeypatch):
    module = load_module()
    token = tmp_path / "api-token"
    token.write_text("test-token\n", encoding="utf-8")
    token.chmod(0o600)

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"success":false,"errors":[{"message":"rejected"}]}'

    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    api = module.CloudflareApi(token)
    with pytest.raises(module.CloudflareApiError) as captured:
        api.request("POST", "/accounts/account/access/apps", {"name": "test"})
    assert captured.value.status == 200
    assert module.is_definitive_mutation_error(captured.value)
    assert module.is_definitive_mutation_error(module.CloudflareApiError("conflict", status=409))
    assert not module.is_definitive_mutation_error(module.CloudflareApiError("server error", status=500))


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
        fail_inventory = 0

        def request(self, method, path, body=None):
            if method == "POST" and path == "/accounts/account/access/apps" and not self.lost:
                self.lost = True
                self.fail_inventory = 2
                super().request(method, path, body)
                raise RuntimeError("connection reset after provider commit")
            if method == "GET" and path == "/accounts/account/access/apps?domain=wizard.example.com&per_page=100" and self.fail_inventory:
                self.fail_inventory -= 1
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

    module.cleanup(module.state_config(recovery), api, token_path, state_path, recovery)
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
        module.cleanup(module.state_config(state), api, token_path, state_path, state)
    assert not api.records
    assert api.tunnels
    assert not api.apps
    assert state_path.exists()

    module.cleanup(module.state_config(state), api, token_path, state_path, state)
    assert not api.tunnels
    assert not state_path.exists()


def test_duplicate_hostname_fails_closed_without_mutation(tmp_path):
    module = load_module()
    api = FakeApi()
    api.apps.append({"id": "foreign", "domain": "wizard.example.com", "type": "self_hosted"})

    with pytest.raises(RuntimeError, match="already has an Access application"):
        module.provision(config(module), api, tmp_path / "token", tmp_path / "state")

    assert not [call for call in api.calls if call[0] in {"POST", "PUT", "DELETE"}]


def test_ambiguous_dns_failure_reconciles_absence_and_rolls_back_created_resources(tmp_path):
    module = load_module()
    api = FakeApi(fail_on=("POST", "/zones/zone/dns_records"))
    token_path = tmp_path / "token"
    state_path = tmp_path / "state.json"

    with pytest.raises(RuntimeError, match="DNS record create result is ambiguous"):
        module.provision(config(module), api, token_path, state_path)

    assert api.deleted == ["tunnel-1", "app-1"]
    assert api.apps == []
    assert api.tunnels == []
    assert not token_path.exists()
    assert not state_path.exists()


@pytest.mark.parametrize("resource", ("app", "tunnel", "dns"))
def test_definitive_409_never_adopts_or_deletes_a_foreign_exact_match(tmp_path, resource):
    module = load_module()

    class ConflictApi(FakeApi):
        def request(self, method, path, body=None):
            target = {
                "app": "/accounts/account/access/apps",
                "tunnel": "/accounts/account/cfd_tunnel",
                "dns": "/zones/zone/dns_records",
            }[resource]
            if method == "POST" and path == target:
                assert isinstance(body, dict)
                if resource == "app":
                    self.apps.append({**body, "id": "foreign-app", "aud": "foreign-aud"})
                elif resource == "tunnel":
                    self.tunnels.append({**body, "id": "foreign-tunnel"})
                else:
                    self.records.append({**body, "id": "foreign-dns"})
                raise module.CloudflareApiError("conflict", status=409)
            return super().request(method, path, body)

    api = ConflictApi()
    state_path = tmp_path / "state.json"
    with pytest.raises(module.CloudflareApiError, match="conflict"):
        module.provision(config(module), api, tmp_path / "token", state_path)

    foreign = {
        "app": api.apps,
        "tunnel": api.tunnels,
        "dns": api.records,
    }[resource]
    assert len(foreign) == 1
    assert foreign[0]["id"].startswith("foreign-")
    assert foreign[0]["id"] not in api.deleted
    assert not state_path.exists()


def test_policy_inventory_must_be_exclusive_before_dns_publication(tmp_path):
    module = load_module()

    class AddedPolicyApi(FakeApi):
        def request(self, method, path, body=None):
            result = super().request(method, path, body)
            if method == "POST" and path.endswith("/access/apps/app-1/policies"):
                self.policies["app-1"].append(
                    {"id": "foreign-bypass", "name": "bypass", "decision": "bypass"}
                )
            return result

    api = AddedPolicyApi()
    state_path = tmp_path / "state.json"
    with pytest.raises(RuntimeError, match="cleanup was incomplete"):
        module.provision(config(module), api, tmp_path / "token", state_path)

    assert not [call for call in api.calls if call[:2] == ("POST", "/zones/zone/dns_records")]
    assert state_path.exists()
    assert len(api.policies["app-1"]) == 2


def test_remote_managed_tunnel_create_payload_has_no_local_tunnel_secret(tmp_path):
    module = load_module()
    api = FakeApi()
    module.provision(config(module), api, tmp_path / "token", tmp_path / "state.json")

    body = next(body for method, path, body in api.calls if method == "POST" and path == "/accounts/account/cfd_tunnel")
    assert set(body) == {"name", "config_src"}
    assert body["config_src"] == "cloudflare"
    assert re.fullmatch(r"HermesUI wizard\.example\.com \[[0-9a-f]{16}\]", body["name"])


def test_recovery_journal_exists_before_first_provider_mutation(tmp_path):
    module = load_module()
    state_path = tmp_path / "state.json"

    class InspectJournalApi(FakeApi):
        def request(self, method, path, body=None):
            if method == "POST" and path == "/accounts/account/access/apps":
                journal = json.loads(state_path.read_text(encoding="utf-8"))
                assert journal["status"] == "recovery_required"
                assert journal["pending_mutation"] == "access_application_create"
                assert re.fullmatch(r"[0-9a-f]{16}", journal["ownership_id"])
                raise module.CloudflareApiError("stop after journal proof", status=400)
            return super().request(method, path, body)

    with pytest.raises(module.CloudflareApiError, match="journal proof"):
        module.provision(config(module), InspectJournalApi(), tmp_path / "token", state_path)


def test_recovery_cleanup_uses_saved_audience_when_app_is_already_absent(tmp_path):
    module = load_module()
    api = FakeApi()
    token_path = tmp_path / "token"
    state_path = tmp_path / "state.json"
    state = module.provision(config(module), api, token_path, state_path)
    api.apps = []
    api.policies = {}
    api.records = []
    state["status"] = "recovery_required"
    state["dns_record_id"] = None
    state_path.write_text(json.dumps(state), encoding="utf-8")

    module.cleanup(module.state_config(state), api, token_path, state_path, state)

    assert not api.tunnels
    assert not state_path.exists()


def test_cleanup_requires_matching_owned_state_and_deletes_in_reverse(tmp_path):
    module = load_module()
    api = FakeApi()
    token_path = tmp_path / "token"
    state_path = tmp_path / "state.json"
    state = module.provision(config(module), api, token_path, state_path)

    module.cleanup(module.state_config(state), api, token_path, state_path, state)

    assert api.deleted[-3:] == ["dns-1", "tunnel-1", "app-1"]
    assert not token_path.exists()
    assert not state_path.exists()


def test_cleanup_refuses_provider_resource_drift_before_any_delete(tmp_path):
    module = load_module()
    api = FakeApi()
    token_path = tmp_path / "token"
    state_path = tmp_path / "state.json"
    state = module.provision(config(module), api, token_path, state_path)
    api.records[0]["content"] = "foreign.example.com"

    with pytest.raises(RuntimeError, match="DNS record no longer matches installer ownership"):
        module.cleanup(module.state_config(state), api, token_path, state_path, state)

    assert not api.deleted
    assert token_path.exists()
    assert state_path.exists()


def test_cleanup_refuses_an_added_access_policy_before_any_delete(tmp_path):
    module = load_module()
    api = FakeApi()
    token_path = tmp_path / "token"
    state_path = tmp_path / "state.json"
    state = module.provision(config(module), api, token_path, state_path)
    api.policies["app-1"].append({"id": "foreign-policy", "decision": "allow"})

    with pytest.raises(RuntimeError, match="Access policies no longer match installer ownership"):
        module.cleanup(module.state_config(state), api, token_path, state_path, state)

    assert not api.deleted
    assert token_path.exists()
    assert state_path.exists()


def test_cleanup_can_preserve_connector_token_and_provider_state_until_local_teardown(tmp_path):
    module = load_module()
    api = FakeApi()
    token_path = tmp_path / "token"
    state_path = tmp_path / "state.json"
    state = module.provision(config(module), api, token_path, state_path)

    module.cleanup(
        module.state_config(state),
        api,
        token_path,
        state_path,
        state,
        preserve_connector_token=True,
        preserve_state=True,
    )

    assert token_path.exists()
    assert stat.S_IMODE(token_path.stat().st_mode) == 0o600
    preserved = json.loads(state_path.read_text(encoding="utf-8"))
    assert preserved["status"] == "provider_resources_removed"

    module.cleanup(module.state_config(preserved), api, token_path, state_path, preserved)
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
    assert f"WorkingDirectory={repo}" in app_unit
    assert f'WorkingDirectory="{repo}"' not in app_unit


def test_systemd_units_pass_real_systemd_analyze_with_a_spaced_repo_path(tmp_path):
    analyzer = shutil.which("systemd-analyze")
    if analyzer is None:
        pytest.skip("systemd-analyze is not installed")
    assert analyzer is not None
    module = load_units_module()
    repo = tmp_path / "Hermes UI"
    home = tmp_path / "home"
    hermes_home = home / ".hermes"
    token = home / ".config" / "hermesui" / "cloudflared.token"
    bin_dir = tmp_path / "bin"
    cloudflared = bin_dir / "cloudflared"
    python = bin_dir / "python3"
    unit_dir = tmp_path / "units"
    for path in (repo, home, hermes_home, token.parent, bin_dir, unit_dir):
        path.mkdir(parents=True, exist_ok=True)
    (repo / "bootstrap.py").write_text("# fixture\n", encoding="utf-8")
    (repo / "hermesui" / "installer").mkdir(parents=True)
    (repo / "hermesui" / "installer" / "runtime-home-guard.py").write_text("# fixture\n", encoding="utf-8")
    token.write_text("not-a-real-token\n", encoding="utf-8")
    token.chmod(0o600)
    for executable in (cloudflared, python):
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)

    app, tunnel = module.render_units(repo, home, hermes_home, python, cloudflared, token, 8793)
    app_path = unit_dir / "hermesui.service"
    tunnel_path = unit_dir / "hermesui-cloudflared.service"
    module._publish_new(app_path, app)
    module._publish_new(tunnel_path, tunnel)

    assert "WorkingDirectory=" + str(repo).replace(" ", "\\x20") in app
    result = subprocess.run(
        [analyzer, "verify", str(app_path), str(tunnel_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_systemd_unit_writer_rejects_a_symlink_destination_without_touching_target(tmp_path):
    module = load_units_module()
    target = tmp_path / "unrelated"
    target.write_text("keep me\n", encoding="utf-8")
    unit_path = tmp_path / "hermesui.service"
    unit_path.symlink_to(target)

    with pytest.raises(FileExistsError):
        module._publish_new(unit_path, "replacement\n")

    assert unit_path.is_symlink()
    assert target.read_text(encoding="utf-8") == "keep me\n"


def test_systemd_unit_removal_restores_a_drifted_unit(tmp_path):
    module = load_units_module()
    unit_path = tmp_path / "hermesui.service"
    unit_path.write_text("foreign unit\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="differs from the specification"):
        module._remove_exact(unit_path, "installer unit\n")

    assert unit_path.read_text(encoding="utf-8") == "foreign unit\n"
    assert not list(tmp_path.glob(".*.hermesui-remove-*"))


def test_systemd_unit_removal_restores_a_symlink_inserted_after_verification(tmp_path, monkeypatch):
    module = load_units_module()
    unit_path = tmp_path / "hermesui.service"
    unit_path.write_text("installer unit\n", encoding="utf-8")
    foreign_target = tmp_path / "foreign"
    foreign_target.write_text("keep me\n", encoding="utf-8")
    real_renameat2 = module._renameat2
    raced = False

    def race(parent_fd, source, destination, flags):
        nonlocal raced
        if not raced and source == unit_path.name and flags == module.RENAME_NOREPLACE:
            raced = True
            unit_path.unlink()
            unit_path.symlink_to(foreign_target)
        return real_renameat2(parent_fd, source, destination, flags)

    monkeypatch.setattr(module, "_renameat2", race)
    with pytest.raises(RuntimeError, match="changed during atomic removal"):
        module._remove_exact(unit_path, "installer unit\n")

    assert unit_path.is_symlink()
    assert unit_path.resolve() == foreign_target
    assert foreign_target.read_text(encoding="utf-8") == "keep me\n"
    assert not list(tmp_path.glob(".*.hermesui-remove-*"))


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
    prompt = (ROOT / "docs/give-this-prompt-to-your-ai.md").read_text(encoding="utf-8")
    legacy_prompt = (ROOT / "docs/Tailnet-HermesUI-Prompt.md").read_text(encoding="utf-8")
    assert prompt == legacy_prompt
    assert "[truncated]" not in prompt
    assert (
        "```text\nInstall Wizard App v0.3.1 from "
        "https://github.com/humanitylabs-org/HermesUI on this Linux Hermes device.\n"
    ) in prompt
    assert "v0.3.1" in prompt
    assert "v0.3.0" not in prompt
    for relative in ("README.md", "docs/give-this-prompt-to-your-ai.md"):
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert "[truncated]" not in content, f"{relative} contains truncated release copy"
        for permission in expected:
            assert permission in content, f"{relative} omits {permission}"
        assert "recovery state" in content, f"{relative} omits ambiguous-mutation recovery guidance"
