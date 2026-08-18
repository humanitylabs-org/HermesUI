#!/usr/bin/env bash
set -euo pipefail

ok() { printf 'OK: %s\n' "$1"; }
fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"; ok "$1 is available"; }

[[ "$(uname -s)" == "Linux" ]] || fail "The automated Tailnet installer currently supports Linux hosts only."

for command_name in python3 git curl systemctl systemd-analyze tailscale hermes; do
  need "$command_name"
done

python3 - <<'PY' || exit 1
import sys
if not ((3, 11) <= sys.version_info[:2] <= (3, 13)):
    print(f"ERROR: Python {sys.version.split()[0]} is unsupported; use Python 3.11, 3.12, or 3.13.", file=sys.stderr)
    raise SystemExit(1)
print(f"OK: Python {sys.version.split()[0]} is supported")
PY

hermes --version >/dev/null 2>&1 || fail "Hermes Agent is installed but 'hermes --version' failed."
ok "Hermes Agent responds"

tailscale status >/dev/null 2>&1 || fail "Tailscale is not connected. Sign in and run 'tailscale up' before continuing."

dns_name="$(tailscale status --self --json 2>/dev/null | python3 -c 'import json,sys; print(((json.load(sys.stdin).get("Self") or {}).get("DNSName") or "").rstrip("."))' 2>/dev/null || true)"
[[ "$dns_name" == *.ts.net ]] || fail "Tailscale MagicDNS hostname was not found. Enable MagicDNS and reconnect."
ok "Tailscale is connected as $dns_name"

systemctl --user show-environment >/dev/null 2>&1 || fail "The systemd user manager is unavailable for this account."
ok "systemd user services are available"

printf '\nAll HermesUI Tailnet prerequisites passed.\n'
