#!/usr/bin/env bash
set -euo pipefail

BASE_PATH="/hermesUI"
SERVICE_NAME="hermesui.service"
LAUNCHER_NAME="hermesui-launcher.service"

SYSTEMD_DIR="${HERMESUI_SYSTEMD_DIR:-${HOME}/.config/systemd/user}"
UNIT_FILE="${SYSTEMD_DIR}/${LAUNCHER_NAME}"
ENABLE_LINK="${SYSTEMD_DIR}/default.target.wants/${LAUNCHER_NAME}"
STATE_DIR="${HERMESUI_STATE_DIR:-${XDG_CONFIG_HOME:-${HOME}/.config}/hermesui}"
STATE_FILE="${STATE_DIR}/install.env"
SYSTEMCTL="${HERMESUI_SYSTEMCTL:-systemctl}"
TAILSCALE="${HERMESUI_TAILSCALE:-tailscale}"
CURL="${HERMESUI_CURL:-curl}"
INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${HERMESUI_REPO_ROOT_OVERRIDE:-$(cd "$INSTALLER_DIR/../.." && pwd)}"
PROCESS_STOP="${HERMESUI_PROCESS_STOP:-${INSTALLER_DIR}/stop-owned-process.py}"
PATH_OP="${HERMESUI_PATH_OP:-${INSTALLER_DIR}/owned-path-op.py}"
LAUNCHER_UNIT="${HERMESUI_LAUNCHER_UNIT_HELPER:-${INSTALLER_DIR}/systemd-launcher-unit.py}"

requested_port="${HERMESUI_PORT:-}"
[[ -r "$STATE_FILE" ]] || { printf 'ERROR: HermesUI install.env is missing or unreadable; ownership cannot be verified.\n' >&2; exit 1; }
saved_port=''
tcp_443_created=''
state_invalid=0
while IFS='=' read -r key value; do
  case "$key" in
    HERMESUI_PORT)
      if [[ -n "$saved_port" ]]; then state_invalid=1; else saved_port="$value"; fi
      ;;
    HERMESUI_TCP_443_CREATED)
      if [[ -n "$tcp_443_created" ]]; then state_invalid=1; else tcp_443_created="$value"; fi
      ;;
    *) state_invalid=1 ;;
  esac
done <"$STATE_FILE"
[[ "$state_invalid" == "0" && "$saved_port" =~ ^[0-9]+$ && "$tcp_443_created" =~ ^[01]$ ]] || { printf 'ERROR: invalid HermesUI install state.\n' >&2; exit 1; }
if [[ -n "$requested_port" && "$requested_port" != "$saved_port" ]]; then
  printf 'ERROR: HERMESUI_PORT does not match the installer-owned port in install.env.\n' >&2
  exit 1
fi
PORT="$saved_port"
if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1024 || PORT > 65535 )); then
  printf 'ERROR: invalid HermesUI port in install.env.\n' >&2
  exit 1
fi
TARGET="http://127.0.0.1:${PORT}"

set +e
unit_fragment="$($SYSTEMCTL --user show "$LAUNCHER_NAME" --property=FragmentPath --value 2>/dev/null)"
status=$?
set -e
if [[ "$status" != "0" ]]; then
  printf 'ERROR: the HermesUI systemd unit provenance could not be queried.\n' >&2
  exit "$status"
fi
[[ "$unit_fragment" == "$UNIT_FILE" && -r "$UNIT_FILE" ]] || {
  printf 'ERROR: the HermesUI launcher is not loaded from the exact managed unit path.\n' >&2
  exit 1
}
"$LAUNCHER_UNIT" verify "$UNIT_FILE" \
  --repo-root "$REPO_ROOT" \
  --home "$HOME" \
  --host 127.0.0.1 \
  --port "$PORT"
unit_digest="$("$PATH_OP" digest "$UNIT_FILE")"
[[ -L "$ENABLE_LINK" && "$("$PATH_OP" readlink "$ENABLE_LINK")" == "$UNIT_FILE" ]] || {
  printf 'ERROR: the HermesUI launcher enablement does not match the managed unit.\n' >&2
  exit 1
}
[[ "$("$PATH_OP" digest "$UNIT_FILE")" == "$unit_digest" ]] || {
  printf 'ERROR: the HermesUI launcher changed while its enablement was verified.\n' >&2
  exit 1
}

"$SYSTEMCTL" --user is-enabled "$LAUNCHER_NAME"
"$SYSTEMCTL" --user is-active "$SERVICE_NAME"
main_pid="$($SYSTEMCTL --user show "$SERVICE_NAME" --property=MainPID --value)"
[[ "$main_pid" =~ ^[0-9]+$ && "$main_pid" -gt 1 ]] || { printf 'ERROR: systemd returned an invalid HermesUI MainPID.\n' >&2; exit 1; }
"$PROCESS_STOP" --pid "$main_pid" --repo-root "$REPO_ROOT" --home "$HOME" --port "$PORT" --systemd-unit "$SERVICE_NAME" --systemctl "$SYSTEMCTL" --verify-only
"$CURL" -fsS --max-time 5 "${TARGET}/health"

dns_name="$($TAILSCALE status --self --json | python3 -c 'import json,sys; print(((json.load(sys.stdin).get("Self") or {}).get("DNSName") or "").rstrip("."))')"
[[ "$dns_name" == *.ts.net ]] || { printf 'ERROR: no Tailscale MagicDNS name found.\n' >&2; exit 1; }
canonical_listener="${dns_name}:443"
serve_status="$($TAILSCALE serve status --json)"
python3 - "$BASE_PATH" "$TARGET" "$serve_status" "$canonical_listener" <<'PY'
import json, sys
path, target, raw, canonical_listener = sys.argv[1:]
config = json.loads(raw)

def configs(value, provenance='top'):
    if not isinstance(value, dict):
        return
    yield value, provenance
    foreground = value.get('Foreground') or {}
    if isinstance(foreground, dict):
        for nested in foreground.values():
            yield from configs(nested, 'foreground')

for value, _ in configs(config):
    if any(enabled is True for enabled in (value.get('AllowFunnel') or {}).values()):
        raise SystemExit('ERROR: Tailscale Funnel is enabled; HermesUI must remain Tailnet-only.')

allowed = {target.rstrip('/'), target.rstrip('/') + path}
found = []
for value, provenance in configs(config):
    web_configs = value.get('Web') or {}
    if not isinstance(web_configs, dict):
        continue
    for listener, web in web_configs.items():
        if listener != canonical_listener:
            continue
        if not isinstance(web, dict):
            continue
        handler = (web.get('Handlers') or {}).get(path)
        if handler is not None:
            proxy = str((handler or {}).get('Proxy') or '').rstrip('/')
            found.append((provenance, proxy))
if not found or any(proxy not in allowed for _, proxy in found):
    raise SystemExit('ERROR: /hermesUI is not routed to this HermesUI service.')
if any(provenance == 'foreground' for provenance, _ in found):
    raise SystemExit('ERROR: /hermesUI has a Foreground or mixed Serve handler; ownership is ambiguous.')
if len(found) != 1:
    raise SystemExit('ERROR: /hermesUI has multiple Serve handlers; ownership is ambiguous.')
PY

public_base="https://${dns_name}${BASE_PATH}/"
"$CURL" -fsS --max-time 8 "${public_base}health"
manifest="$($CURL -fsS --max-time 8 "${public_base}manifest.json")"
python3 - "$manifest" <<'PY'
import json, sys
manifest = json.loads(sys.argv[1])
if manifest.get('name') != 'HermesUI':
    raise SystemExit('ERROR: canonical HermesUI manifest did not identify HermesUI.')
for key in ('id', 'start_url', 'scope'):
    if not str(manifest.get(key, '')).startswith('./'):
        raise SystemExit(f'ERROR: canonical HermesUI manifest {key} is not subpath-relative.')
PY
printf '\nHermesUI URL: %s\n' "$public_base"
