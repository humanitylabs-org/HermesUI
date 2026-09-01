#!/usr/bin/env bash
set -euo pipefail

ok() { printf 'OK: %s\n' "$1"; }
fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"; ok "$1 is available"; }

[[ "$(uname -s)" == "Linux" ]] || fail "The Cloudflare installer supports Linux VPS hosts only."
for command_name in python3 git curl systemctl systemd-analyze loginctl flock cloudflared hermes; do
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
hermes doctor >/dev/null 2>&1 || fail "'hermes doctor' reported an unhealthy Hermes installation."
ok "Hermes Agent responds and doctor passes"
cloudflared --version >/dev/null 2>&1 || fail "cloudflared is installed but its version check failed."
ok "cloudflared responds"
systemctl --user show-environment >/dev/null 2>&1 || fail "The systemd user manager is unavailable for this account."
ok "systemd user services are available"
linger="$(loginctl show-user "$(id -u)" --property=Linger --value 2>/dev/null || true)"
login_name="$(id -un)"
[[ "$linger" == yes ]] || fail "User lingering is disabled. Ask before running: sudo loginctl enable-linger $(printf '%q' "$login_name")"
ok "systemd user services will survive logout and reboot"
printf '\nAll Wizard App Cloudflare prerequisites passed.\n'
