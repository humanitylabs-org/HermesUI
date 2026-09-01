#!/usr/bin/env python3
"""Provision a fail-closed Cloudflare Tunnel + Access boundary for HermesUI."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = "https://api.cloudflare.com/client/v4"
HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class CloudflareApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class AmbiguousMutationError(RuntimeError):
    pass


class ProvisionConfig:
    def __init__(
        self,
        account_id: str,
        zone_id: str,
        hostname: str,
        allowed_emails: tuple[str, ...],
        origin_url: str,
        tunnel_name: str,
    ) -> None:
        hostname = hostname.strip().lower().rstrip(".")
        emails = tuple(dict.fromkeys(email.strip().lower() for email in allowed_emails))
        if not ID_RE.fullmatch(account_id):
            raise ValueError("invalid Cloudflare account id")
        if not ID_RE.fullmatch(zone_id):
            raise ValueError("invalid Cloudflare zone id")
        if not HOSTNAME_RE.fullmatch(hostname):
            raise ValueError("invalid hostname; provide a DNS hostname without a scheme or path")
        if not emails or any(not EMAIL_RE.fullmatch(email) for email in emails):
            raise ValueError("each allowed email must be an exact email address")
        parsed = urllib.parse.urlsplit(origin_url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port or parsed.path not in {"", "/"}:
            raise ValueError("origin must be a loopback HTTP URL with an explicit port")
        if not tunnel_name.strip() or len(tunnel_name) > 100:
            raise ValueError("invalid tunnel name")
        self.account_id = account_id
        self.zone_id = zone_id
        self.hostname = hostname
        self.allowed_emails = emails
        self.origin_url = origin_url.rstrip("/")
        self.tunnel_name = tunnel_name.strip()


class CloudflareApi:
    def __init__(self, token_file: Path, *, base_url: str = API_BASE, timeout: int = 30) -> None:
        self.token = read_secret_file(token_file)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request_envelope(self, method: str, path: str, body: Any = None) -> dict[str, Any]:
        payload = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=payload,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "HermesUI-Cloudflare-Installer/1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                detail = json.loads(raw.decode("utf-8"))
                messages = detail.get("errors") or detail.get("messages") or []
                safe = "; ".join(str(item.get("message", "provider error")) for item in messages if isinstance(item, dict))
            except Exception:
                safe = "provider request failed"
            raise CloudflareApiError(
                f"Cloudflare API {method} {path} failed with HTTP {exc.code}: {safe}",
                status=exc.code,
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cloudflare API {method} {path} was unreachable: {exc.reason}") from exc
        if not raw:
            return {"success": True, "result": None}
        envelope = json.loads(raw.decode("utf-8"))
        if not isinstance(envelope, dict) or envelope.get("success") is not True:
            raise RuntimeError(f"Cloudflare API {method} {path} returned an unsuccessful response")
        return envelope

    def request(self, method: str, path: str, body: Any = None) -> Any:
        envelope = self._request_envelope(method, path, body)
        return envelope.get("result")

    def list_all(self, path: str) -> list[Any]:
        results: list[Any] = []
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            paged_path = f"{path}{separator}page={page}"
            envelope = self._request_envelope("GET", paged_path)
            batch = envelope.get("result")
            if not isinstance(batch, list):
                raise RuntimeError(f"Cloudflare API GET {paged_path} did not return a resource list")
            results.extend(batch)
            info = envelope.get("result_info")
            if not isinstance(info, dict):
                break
            total_pages = info.get("total_pages")
            if isinstance(total_pages, int) and total_pages >= 1:
                if page >= total_pages:
                    break
                page += 1
                continue
            total_count = info.get("total_count")
            per_page = info.get("per_page")
            current_page = info.get("page", page)
            if (
                isinstance(total_count, int)
                and isinstance(per_page, int)
                and per_page >= 1
                and isinstance(current_page, int)
                and current_page * per_page < total_count
            ):
                page = current_page + 1
                continue
            break
        return results


def read_secret_file(path: Path) -> str:
    path = path.expanduser()
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RuntimeError("Cloudflare API token path must be a regular non-symlink file")
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise RuntimeError("Cloudflare API token file must be owned by the current user with mode 0600")
    value = path.read_text(encoding="utf-8").strip()
    if not value or "\n" in value or "\r" in value:
        raise RuntimeError("Cloudflare API token file must contain exactly one non-empty token")
    return value


def atomic_write(path: Path, content: str, mode: int) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def api_paths(config: ProvisionConfig) -> dict[str, str]:
    account = config.account_id
    zone = config.zone_id
    encoded_hostname = urllib.parse.quote(config.hostname, safe="")
    encoded_tunnel_name = urllib.parse.quote(config.tunnel_name, safe="")
    return {
        "org": f"/accounts/{account}/access/organizations",
        "idps": f"/accounts/{account}/access/identity_providers?per_page=100",
        "apps": f"/accounts/{account}/access/apps?domain={encoded_hostname}&per_page=100",
        "app_create": f"/accounts/{account}/access/apps",
        "tunnels": f"/accounts/{account}/cfd_tunnel?is_deleted=false&name={encoded_tunnel_name}&per_page=100",
        "tunnel_create": f"/accounts/{account}/cfd_tunnel",
        "dns": f"/zones/{zone}/dns_records?name={encoded_hostname}&per_page=100",
        "dns_create": f"/zones/{zone}/dns_records",
    }


def desired_app(config: ProvisionConfig, idps: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [item.get("id") for item in idps if isinstance(item, dict) and isinstance(item.get("id"), str)]
    if not ids:
        raise RuntimeError("Cloudflare Access has no configured identity provider")
    return {
        "name": f"HermesUI — {config.hostname}",
        "domain": config.hostname,
        "type": "self_hosted",
        "session_duration": "24h",
        "allowed_idps": ids,
        "auto_redirect_to_identity": len(ids) == 1,
        "app_launcher_visible": False,
        "allow_iframe": True,
    }


def desired_policy(config: ProvisionConfig) -> dict[str, Any]:
    return {
        "name": "HermesUI owners",
        "decision": "allow",
        "session_duration": "24h",
        "include": [{"email": {"email": email}} for email in config.allowed_emails],
        "exclude": [],
        "require": [],
    }


def desired_tunnel_config(config: ProvisionConfig, auth_domain: str, audience: str) -> dict[str, Any]:
    if not isinstance(auth_domain, str) or not auth_domain.endswith(".cloudflareaccess.com"):
        raise RuntimeError("Cloudflare Access organization did not return a valid auth domain")
    if not isinstance(audience, str) or not audience:
        raise RuntimeError("Cloudflare Access application did not return an audience tag")
    return {
        "config": {
            "ingress": [
                {
                    "hostname": config.hostname,
                    "service": config.origin_url,
                    "originRequest": {
                        "access": {
                            "required": True,
                            "teamName": auth_domain.split(".", 1)[0],
                            "audTag": [audience],
                        }
                    },
                },
                {"service": "http_status:404"},
            ],
            "warp-routing": {"enabled": False},
        }
    }


def matching(items: Any, **fields: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise RuntimeError("Cloudflare API returned an invalid inventory")
    return [item for item in items if isinstance(item, dict) and all(item.get(key) == value for key, value in fields.items())]


def listed(api: Any, path: str) -> list[Any]:
    if hasattr(api, "list_all"):
        return api.list_all(path)
    result = api.request("GET", path)
    if not isinstance(result, list):
        raise RuntimeError("Cloudflare API returned an invalid inventory")
    return result


def exact_fields(actual: dict[str, Any], expected: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return all(actual.get(field) == expected.get(field) for field in fields)


def create_or_recover(
    *,
    label: str,
    create: Any,
    inventory: Any,
    is_exact: Any,
    independent: bool = False,
    required_fields: tuple[str, ...] = ("id",),
) -> dict[str, Any]:
    original: Exception
    try:
        created = create()
        if (
            isinstance(created, dict)
            and all(isinstance(created.get(field), str) and created[field] for field in required_fields)
        ):
            return created
        original = RuntimeError(f"Cloudflare returned an incomplete {label} create response")
    except Exception as create_error:
        original = create_error
    try:
        candidates = [
            item
            for item in inventory()
            if isinstance(item, dict)
            and is_exact(item)
            and all(isinstance(item.get(field), str) and item[field] for field in required_fields)
        ]
    except Exception as reconcile_error:
        error_type = AmbiguousMutationError if independent else RuntimeError
        raise error_type(
            f"{label} create result is ambiguous and provider reconciliation failed; do not retry blindly"
        ) from reconcile_error
    if len(candidates) != 1:
        error_type = AmbiguousMutationError if independent else RuntimeError
        raise error_type(
            f"{label} create result is ambiguous and exact provider reconciliation did not find one resource; do not retry blindly"
        ) from original
    return candidates[0]


def recovery_state(config: ProvisionConfig, created: dict[str, str | None]) -> dict[str, Any]:
    return {
        "version": 1,
        "status": "recovery_required",
        "account_id": config.account_id,
        "zone_id": config.zone_id,
        "hostname": config.hostname,
        "origin_url": config.origin_url,
        "allowed_emails": list(config.allowed_emails),
        "access_app_id": created.get("app"),
        "access_policy_id": created.get("policy"),
        "tunnel_id": created.get("tunnel"),
        "tunnel_name": config.tunnel_name,
        "dns_record_id": created.get("dns"),
        "managed": {"access_app": True, "dns_record": True, "tunnel": True},
    }


def provision(
    config: ProvisionConfig,
    api: Any,
    token_path: Path,
    state_path: Path,
) -> dict[str, Any]:
    paths = api_paths(config)
    if token_path.exists() or state_path.exists():
        raise RuntimeError("Cloudflare installer state already exists; run status or uninstall instead of overwriting it")

    organization = api.request("GET", paths["org"])
    idps = listed(api, paths["idps"])
    applications = matching(listed(api, paths["apps"]), domain=config.hostname, type="self_hosted")
    tunnels = matching(listed(api, paths["tunnels"]), name=config.tunnel_name)
    records = matching(listed(api, paths["dns"]), name=config.hostname)
    if applications:
        raise RuntimeError("hostname already has an Access application; refusing to take ownership")
    if tunnels:
        raise RuntimeError("tunnel name already exists; refusing to take ownership")
    if records:
        raise RuntimeError("hostname already has a DNS record; refusing to take ownership")
    if not isinstance(organization, dict):
        raise RuntimeError("Cloudflare Access organization is not configured")

    created: dict[str, str | None] = {"app": None, "policy": None, "tunnel": None, "dns": None}
    try:
        desired_application = desired_app(config, idps)
        app = create_or_recover(
            label="Access application",
            create=lambda: api.request("POST", paths["app_create"], desired_application),
            inventory=lambda: listed(api, paths["apps"]),
            is_exact=lambda item: exact_fields(
                item,
                desired_application,
                ("domain", "type", "session_duration", "allowed_idps", "auto_redirect_to_identity", "app_launcher_visible", "allow_iframe"),
            ),
            independent=True,
            required_fields=("id", "aud"),
        )
        if not isinstance(app.get("id"), str) or not isinstance(app.get("aud"), str):
            raise RuntimeError("Cloudflare did not return a valid Access application")
        created["app"] = app["id"]

        policy_path = f"/accounts/{config.account_id}/access/apps/{app['id']}/policies"
        desired_access_policy = desired_policy(config)
        policy = create_or_recover(
            label="Access policy",
            create=lambda: api.request("POST", policy_path, desired_access_policy),
            inventory=lambda: listed(api, policy_path + "?per_page=100"),
            is_exact=lambda item: exact_fields(
                item,
                desired_access_policy,
                ("decision", "session_duration", "include", "exclude", "require"),
            ),
        )
        if not isinstance(policy.get("id"), str):
            raise RuntimeError("Cloudflare did not return a valid Access policy")
        created["policy"] = policy["id"]

        tunnel_secret = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        desired_tunnel = {"name": config.tunnel_name, "tunnel_secret": tunnel_secret, "config_src": "cloudflare"}
        tunnel = create_or_recover(
            label="tunnel",
            create=lambda: api.request("POST", paths["tunnel_create"], desired_tunnel),
            inventory=lambda: listed(api, paths["tunnels"]),
            is_exact=lambda item: item.get("name") == config.tunnel_name and item.get("config_src") == "cloudflare",
            independent=True,
        )
        if not isinstance(tunnel.get("id"), str):
            raise RuntimeError("Cloudflare did not return a valid tunnel")
        created["tunnel"] = tunnel["id"]

        tunnel_config_path = f"/accounts/{config.account_id}/cfd_tunnel/{tunnel['id']}/configurations"
        expected_config = desired_tunnel_config(config, organization.get("auth_domain", ""), app["aud"])
        try:
            api.request("PUT", tunnel_config_path, expected_config)
        except Exception as original:
            config_after_error = api.request("GET", tunnel_config_path)
            if not isinstance(config_after_error, dict) or config_after_error.get("config") != expected_config["config"]:
                raise RuntimeError(
                    "tunnel configuration update result is ambiguous and exact provider reconciliation failed; do not retry blindly"
                ) from original
        config_readback = api.request("GET", tunnel_config_path)
        if not isinstance(config_readback, dict) or config_readback.get("config") != expected_config["config"]:
            raise RuntimeError("Cloudflare tunnel configuration read-back mismatch")

        desired_dns = {
            "type": "CNAME",
            "name": config.hostname,
            "content": f"{tunnel['id']}.cfargotunnel.com",
            "proxied": True,
            "ttl": 1,
        }
        dns = create_or_recover(
            label="DNS record",
            create=lambda: api.request("POST", paths["dns_create"], desired_dns),
            inventory=lambda: listed(api, paths["dns"]),
            is_exact=lambda item: exact_fields(item, desired_dns, ("type", "name", "content", "proxied", "ttl")),
            independent=True,
        )
        if not isinstance(dns.get("id"), str):
            raise RuntimeError("Cloudflare did not return a valid DNS record")
        created["dns"] = dns["id"]

        app_readback = matching(listed(api, paths["apps"]), domain=config.hostname, type="self_hosted")
        policy_readback = listed(api, policy_path + "?per_page=100")
        tunnel_readback = matching(listed(api, paths["tunnels"]), name=config.tunnel_name)
        dns_readback = matching(listed(api, paths["dns"]), name=config.hostname)
        if (
            len(app_readback) != 1
            or app_readback[0].get("id") != app["id"]
            or not exact_fields(
                app_readback[0],
                desired_application,
                ("domain", "type", "session_duration", "allowed_idps", "auto_redirect_to_identity", "app_launcher_visible", "allow_iframe"),
            )
        ):
            raise RuntimeError("Access application read-back mismatch")
        matching_policies = matching(policy_readback, id=policy["id"])
        if (
            len(matching_policies) != 1
            or not exact_fields(
                matching_policies[0],
                desired_access_policy,
                ("decision", "session_duration", "include", "exclude", "require"),
            )
        ):
            raise RuntimeError("Access policy read-back mismatch")
        if (
            len(tunnel_readback) != 1
            or tunnel_readback[0].get("id") != tunnel["id"]
            or tunnel_readback[0].get("name") != config.tunnel_name
            or tunnel_readback[0].get("config_src") != "cloudflare"
        ):
            raise RuntimeError("tunnel read-back mismatch")
        if (
            len(dns_readback) != 1
            or dns_readback[0].get("id") != dns["id"]
            or not exact_fields(dns_readback[0], desired_dns, ("type", "name", "content", "proxied", "ttl"))
        ):
            raise RuntimeError("DNS read-back mismatch")

        connector_token = api.request("GET", f"/accounts/{config.account_id}/cfd_tunnel/{tunnel['id']}/token")
        if not isinstance(connector_token, str) or not connector_token:
            raise RuntimeError("Cloudflare did not return a connector token")
        atomic_write(token_path, connector_token + "\n", 0o600)
        state = {
            "version": 1,
            "account_id": config.account_id,
            "zone_id": config.zone_id,
            "hostname": config.hostname,
            "origin_url": config.origin_url,
            "allowed_emails": list(config.allowed_emails),
            "auth_domain": organization["auth_domain"],
            "access_app_id": app["id"],
            "access_policy_id": policy["id"],
            "tunnel_id": tunnel["id"],
            "tunnel_name": config.tunnel_name,
            "dns_record_id": dns["id"],
            "managed": {"access_app": True, "dns_record": True, "tunnel": True},
        }
        atomic_write(state_path, json.dumps(state, sort_keys=True, indent=2) + "\n", 0o600)
        return state
    except BaseException as original:
        atomic_write(state_path, json.dumps(recovery_state(config, created), sort_keys=True, indent=2) + "\n", 0o600)
        try:
            _rollback_created(config, api, created)
        except Exception as cleanup_error:
            token_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Cloudflare provisioning failed and cleanup was incomplete; recovery state was retained at {state_path}"
            ) from cleanup_error
        token_path.unlink(missing_ok=True)
        if isinstance(original, AmbiguousMutationError):
            raise RuntimeError(f"{original}; recovery state was retained at {state_path}") from original
        state_path.unlink(missing_ok=True)
        raise


def _delete_managed(api: Any, operations: tuple[tuple[str, str], ...]) -> None:
    errors: list[tuple[str, Exception]] = []
    for label, path in operations:
        try:
            api.request("DELETE", path)
        except Exception as exc:
            if getattr(exc, "status", None) == 404:
                continue
            errors.append((label, exc))
    if errors:
        labels = ", ".join(label for label, _ in errors)
        raise RuntimeError(
            f"Cloudflare cleanup was incomplete for: {labels}; state was retained for a safe retry"
        ) from errors[0][1]


def _rollback_created(config: ProvisionConfig, api: Any, created: dict[str, str | None]) -> None:
    operations = []
    if created.get("dns"):
        operations.append(("DNS record", f"/zones/{config.zone_id}/dns_records/{created['dns']}"))
    if created.get("tunnel"):
        operations.append(("tunnel", f"/accounts/{config.account_id}/cfd_tunnel/{created['tunnel']}"))
    if created.get("app"):
        operations.append(("Access application", f"/accounts/{config.account_id}/access/apps/{created['app']}"))
    _delete_managed(api, tuple(operations))


def cleanup(
    config: ProvisionConfig,
    api: Any,
    token_path: Path,
    state_path: Path,
    state: dict[str, Any],
) -> None:
    expected = {
        "account_id": config.account_id,
        "zone_id": config.zone_id,
        "hostname": config.hostname,
        "origin_url": config.origin_url,
        "allowed_emails": list(config.allowed_emails),
        "tunnel_name": config.tunnel_name,
    }
    if state.get("version") != 1 or any(state.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Cloudflare state does not match the requested install; refusing cleanup")
    managed = state.get("managed")
    if managed != {"access_app": True, "dns_record": True, "tunnel": True}:
        raise RuntimeError("Cloudflare state does not claim exact managed ownership")
    recovery_mode = state.get("status") == "recovery_required"
    if not recovery_mode:
        for key in ("access_app_id", "access_policy_id", "tunnel_id", "dns_record_id"):
            if not isinstance(state.get(key), str) or not state[key]:
                raise RuntimeError("Cloudflare state is incomplete")

    paths = api_paths(config)
    if recovery_mode and not state.get("access_app_id"):
        app_candidates = matching(listed(api, paths["apps"]), domain=config.hostname, type="self_hosted")
        if app_candidates:
            expected_app = desired_app(config, listed(api, paths["idps"]))
            exact_apps = [
                item
                for item in app_candidates
                if exact_fields(
                    item,
                    expected_app,
                    ("domain", "type", "session_duration", "allowed_idps", "auto_redirect_to_identity", "app_launcher_visible", "allow_iframe"),
                )
            ]
            if len(app_candidates) != 1 or len(exact_apps) != 1 or not isinstance(exact_apps[0].get("id"), str):
                raise RuntimeError("Access application recovery inventory is ambiguous; refusing cleanup")
            state["access_app_id"] = exact_apps[0]["id"]
    if recovery_mode and not state.get("tunnel_id"):
        tunnel_candidates = matching(listed(api, paths["tunnels"]), name=config.tunnel_name)
        exact_tunnels = [item for item in tunnel_candidates if item.get("config_src") == "cloudflare"]
        if tunnel_candidates:
            if len(tunnel_candidates) != 1 or len(exact_tunnels) != 1 or not isinstance(exact_tunnels[0].get("id"), str):
                raise RuntimeError("tunnel recovery inventory is ambiguous; refusing cleanup")
            state["tunnel_id"] = exact_tunnels[0]["id"]
    if recovery_mode and not state.get("dns_record_id"):
        dns_candidates = matching(listed(api, paths["dns"]), name=config.hostname)
        if dns_candidates:
            tunnel_id = state.get("tunnel_id")
            expected_dns = {
                "type": "CNAME",
                "name": config.hostname,
                "content": f"{tunnel_id}.cfargotunnel.com",
                "proxied": True,
                "ttl": 1,
            }
            exact_dns = [
                item
                for item in dns_candidates
                if isinstance(tunnel_id, str)
                and exact_fields(item, expected_dns, ("type", "name", "content", "proxied", "ttl"))
            ]
            if len(dns_candidates) != 1 or len(exact_dns) != 1 or not isinstance(exact_dns[0].get("id"), str):
                raise RuntimeError("DNS recovery inventory is ambiguous; refusing cleanup")
            state["dns_record_id"] = exact_dns[0]["id"]

    operations = []
    if isinstance(state.get("dns_record_id"), str) and state["dns_record_id"]:
        operations.append(("DNS record", f"/zones/{config.zone_id}/dns_records/{state['dns_record_id']}"))
    if isinstance(state.get("tunnel_id"), str) and state["tunnel_id"]:
        operations.append(("tunnel", f"/accounts/{config.account_id}/cfd_tunnel/{state['tunnel_id']}"))
    if isinstance(state.get("access_app_id"), str) and state["access_app_id"]:
        operations.append(("Access application", f"/accounts/{config.account_id}/access/apps/{state['access_app_id']}"))
    _delete_managed(api, tuple(operations))
    if matching(listed(api, paths["dns"]), name=config.hostname):
        raise RuntimeError("DNS record still exists after cleanup")
    if matching(listed(api, paths["tunnels"]), name=config.tunnel_name):
        raise RuntimeError("tunnel still exists after cleanup")
    if matching(listed(api, paths["apps"]), domain=config.hostname, type="self_hosted"):
        raise RuntimeError("Access application still exists after cleanup")
    token_path.unlink(missing_ok=True)
    state_path.unlink(missing_ok=True)


def state_config(state: dict[str, Any]) -> ProvisionConfig:
    return ProvisionConfig(
        account_id=state.get("account_id", ""),
        zone_id=state.get("zone_id", ""),
        hostname=state.get("hostname", ""),
        allowed_emails=tuple(state.get("allowed_emails") or ()),
        origin_url=state.get("origin_url", ""),
        tunnel_name=state.get("tunnel_name", ""),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--account-id", required=True)
    apply_parser.add_argument("--zone-id", required=True)
    apply_parser.add_argument("--hostname", required=True)
    apply_parser.add_argument("--allow-email", action="append", required=True)
    apply_parser.add_argument("--origin-url", required=True)
    apply_parser.add_argument("--tunnel-name", required=True)
    cleanup_parser = sub.add_parser("cleanup")
    for child in (apply_parser, cleanup_parser):
        child.add_argument("--api-token-file", type=Path, required=True)
        child.add_argument("--connector-token-file", type=Path, required=True)
        child.add_argument("--state-file", type=Path, required=True)
        child.add_argument("--api-base", default=os.environ.get("HERMESUI_CLOUDFLARE_API_BASE", API_BASE))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        api = CloudflareApi(args.api_token_file, base_url=args.api_base)
        if args.action == "apply":
            config = ProvisionConfig(
                args.account_id,
                args.zone_id,
                args.hostname,
                tuple(args.allow_email),
                args.origin_url,
                args.tunnel_name,
            )
            state = provision(config, api, args.connector_token_file, args.state_file)
            print(f"Cloudflare private access staged for https://{state['hostname']}/")
        else:
            state = json.loads(args.state_file.read_text(encoding="utf-8"))
            config = state_config(state)
            cleanup(config, api, args.connector_token_file, args.state_file, state)
            print("Cloudflare resources removed")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
