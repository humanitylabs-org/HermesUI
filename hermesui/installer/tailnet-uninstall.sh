#!/usr/bin/env bash
set -euo pipefail

INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${HERMESUI_REPO_ROOT_OVERRIDE:-$(cd "$INSTALLER_DIR/../.." && pwd)}"
BASE_PATH="/hermesUI"
SERVICE_NAME="hermesui.service"
LAUNCHER_NAME="hermesui-launcher.service"

SYSTEMD_DIR="${HERMESUI_SYSTEMD_DIR:-${HOME}/.config/systemd/user}"
UNIT_FILE="${SYSTEMD_DIR}/${LAUNCHER_NAME}"
ENABLE_DIR="${SYSTEMD_DIR}/default.target.wants"
ENABLE_LINK="${ENABLE_DIR}/${LAUNCHER_NAME}"
STATE_DIR="${HERMESUI_STATE_DIR:-${XDG_CONFIG_HOME:-${HOME}/.config}/hermesui}"
STATE_FILE="${STATE_DIR}/install.env"
SYSTEMCTL="${HERMESUI_SYSTEMCTL:-systemctl}"
TAILSCALE="${HERMESUI_TAILSCALE:-tailscale}"
PATH_OP="${HERMESUI_PATH_OP:-${INSTALLER_DIR}/owned-path-op.py}"
SERVE_CAS="${HERMESUI_SERVE_CAS_HELPER:-${INSTALLER_DIR}/tailscale-serve-cas.py}"
PROCESS_STOP="${HERMESUI_PROCESS_STOP:-${INSTALLER_DIR}/stop-owned-process.py}"
SERVICE_START="${HERMESUI_SERVICE_START:-${INSTALLER_DIR}/systemd-start-owned.py}"
LAUNCHER_UNIT="${HERMESUI_LAUNCHER_UNIT_HELPER:-${INSTALLER_DIR}/systemd-launcher-unit.py}"
LOCK_HELPER="${HERMESUI_LIFECYCLE_LOCK_HELPER:-${INSTALLER_DIR}/acquire-lifecycle-lock.py}"
SYSTEMD_RUN="${HERMESUI_SYSTEMD_RUN:-systemd-run}"
LIFECYCLE_LOCK="${HERMESUI_LIFECYCLE_LOCK_FILE:-${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/hermesui-${UID}/lifecycle.lock}"

if [[ "${HERMESUI_LIFECYCLE_LOCK_HELD:-0}" == "1" ]]; then
  python3 "$LOCK_HELPER" --lock "$LIFECYCLE_LOCK" --fd 9 --verify-inherited || exit 75
else
  exec python3 "$LOCK_HELPER" --lock "$LIFECYCLE_LOCK" --fd 9 -- "$INSTALLER_DIR/tailnet-uninstall.sh" "$@"
fi

file_digest() {
  "$PATH_OP" digest "$1"
}

serve_cas() {
  local expected="${1:-absent}" desired="${2:-absent}" remove_tcp="${3:-0}"
  local -a args
  if [[ -n "${HERMESUI_TAILSCALE:-}" && -z "${HERMESUI_SERVE_CAS_HELPER:-}" ]]; then
    printf 'ERROR: HERMESUI_TAILSCALE is overridden; HERMESUI_SERVE_CAS_HELPER is required for atomic route changes.\n' >&2
    return 1
  fi
  args=(--listener "$CANONICAL_LISTENER" --path "$BASE_PATH" --expected "$expected" --desired "$desired")
  [[ "$remove_tcp" != "1" ]] || args+=(--remove-tcp-if-owned)
  "$SERVE_CAS" "${args[@]}"
}

unit_is_owned() {
  "$LAUNCHER_UNIT" verify "$1" \
    --repo-root "$REPO_ROOT" \
    --home "$HOME" \
    --host 127.0.0.1 \
    --port "$PORT"
}

inspect_route() {
  python3 - "$BASE_PATH" "$TARGET" "$1" "$CANONICAL_LISTENER" <<'PY'
import json, sys

path, target, raw, canonical_listener = sys.argv[1:]
try:
    root = json.loads(raw)
except Exception:
    print('unknown')
    raise SystemExit

allowed = {target.rstrip('/'), target.rstrip('/') + path}
matches = []

def configs(value, provenance='top'):
    if not isinstance(value, dict):
        return
    yield value, provenance
    foreground = value.get('Foreground') or {}
    if isinstance(foreground, dict):
        for nested in foreground.values():
            yield from configs(nested, 'foreground')

for value, provenance in configs(root):
    web_configs = value.get('Web') or {}
    if not isinstance(web_configs, dict):
        continue
    for listener, web in web_configs.items():
        if listener != canonical_listener:
            continue
        if not isinstance(web, dict):
            continue
        handler = (web.get('Handlers') or {}).get(path)
        if handler is None:
            continue
        proxy = str((handler or {}).get('Proxy') or '').rstrip('/')
        matches.append((provenance, proxy in allowed))

if not matches:
    print('missing')
elif any(provenance == 'foreground' and owned for provenance, owned in matches):
    print('ambiguous-foreground')
elif any(provenance == 'top' and owned for provenance, owned in matches) and any(not owned for _, owned in matches):
    print('ambiguous-mixed')
elif any(provenance == 'top' and owned for provenance, owned in matches):
    print('owned-top')
else:
    print('foreign')
PY
}

state_owned=0
state_preimage_digest=""
PORT="${HERMESUI_PORT:-}"
tcp_443_created=''
if [[ -e "$STATE_FILE" ]]; then
  if [[ ! -r "$STATE_FILE" ]]; then
    printf 'ERROR: HermesUI install state is unreadable; refusing an ownership-ambiguous uninstall.\n' >&2
    exit 1
  fi
  saved_port=''
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
  if [[ "$state_invalid" == "0" && "$saved_port" =~ ^[0-9]+$ && "$tcp_443_created" =~ ^[01]$ ]]; then
    if [[ -n "$PORT" && "$PORT" != "$saved_port" ]]; then
      printf 'ERROR: HERMESUI_PORT does not match the installer-owned port in install.env. Nothing was changed.\n' >&2
      exit 1
    fi
    PORT="$saved_port"
    state_owned=1
    state_preimage_digest="$(file_digest "$STATE_FILE")"
  else
    printf 'ERROR: HermesUI install state is invalid; refusing an ownership-ambiguous uninstall.\n' >&2
    exit 1
  fi
fi
PORT="${PORT:-8793}"
if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1024 || PORT > 65535 )); then
  printf 'ERROR: HERMESUI_PORT must be an unprivileged TCP port from 1024 through 65535.\n' >&2
  exit 1
fi
TARGET="http://127.0.0.1:${PORT}"

unit_owned=0
unit_preimage_digest=""
if existing_fragment="$($SYSTEMCTL --user show "$LAUNCHER_NAME" --property=FragmentPath --value 2>/dev/null)"; then
  :
else
  fragment_status=$?
  printf 'ERROR: Could not verify the systemd provenance of %s. Nothing was changed.\n' "$LAUNCHER_NAME" >&2
  exit "$fragment_status"
fi
if [[ -n "$existing_fragment" && "$existing_fragment" != "$UNIT_FILE" ]]; then
  printf 'ERROR: %s is loaded from %s, outside the HermesUI-managed unit path. Nothing was changed.\n' "$LAUNCHER_NAME" "$existing_fragment" >&2
  exit 1
fi
if [[ -e "$UNIT_FILE" ]] && ! unit_is_owned "$UNIT_FILE"; then
  printf 'ERROR: %s is not managed by HermesUI. Nothing was changed.\n' "$UNIT_FILE" >&2
  exit 1
fi
if [[ -e "$UNIT_FILE" ]]; then
  unit_owned=1
  unit_preimage_digest="$(file_digest "$UNIT_FILE")"
fi
if [[ "$unit_owned" == "1" && "$state_owned" != "1" ]]; then
  printf 'ERROR: %s is managed by HermesUI, but install.env is missing. The port and route ownership cannot be verified, so nothing was changed.\n' "$LAUNCHER_NAME" >&2
  exit 1
fi

enable_link_owned=0
if [[ -L "$ENABLE_LINK" ]]; then
  if [[ "$("$PATH_OP" readlink "$ENABLE_LINK")" != "$UNIT_FILE" ]]; then
    printf 'ERROR: The default.target enable link for %s is foreign. Nothing was changed.\n' "$LAUNCHER_NAME" >&2
    exit 1
  fi
  enable_link_owned=1
elif [[ -e "$ENABLE_LINK" ]]; then
  printf 'ERROR: The default.target enable path for %s is not a HermesUI-managed symlink. Nothing was changed.\n' "$LAUNCHER_NAME" >&2
  exit 1
fi

dns_name="$($TAILSCALE status --self --json 2>/dev/null | python3 -c 'import json,sys; print(((json.load(sys.stdin).get("Self") or {}).get("DNSName") or "").rstrip("."))')"
if [[ "$dns_name" != *.ts.net ]]; then
  printf 'ERROR: no Tailscale MagicDNS name was available, so route ownership could not be verified. Nothing was changed.\n' >&2
  exit 1
fi
CANONICAL_LISTENER="${dns_name}:443"
if ! serve_status="$($TAILSCALE serve status --json 2>/dev/null)"; then
  printf 'ERROR: Tailscale Serve status was unavailable, so nothing was changed.\n' >&2
  exit 1
fi
route_kind="$(inspect_route "$serve_status")"
case "$route_kind" in
  owned-top)
    if [[ "$state_owned" != "1" ]]; then
      printf 'ERROR: %s matches HermesUI but has no installer ownership state. It may be a manual route, so nothing was changed.\n' "$BASE_PATH" >&2
      exit 1
    fi
    route_action="remove"
    ;;
  missing) route_action="absent" ;;
  foreign) route_action="preserve" ;;
  ambiguous-foreground|ambiguous-mixed)
    printf 'ERROR: %s has foreground or mixed ownership that a background uninstall cannot safely remove. Nothing was changed.\n' "$BASE_PATH" >&2
    exit 1
    ;;
  *)
    printf 'ERROR: Serve ownership could not be verified, so nothing was changed.\n' >&2
    exit 1
    ;;
esac

unit_matches_preimage() {
  [[ "$unit_owned" == "1" && -e "$UNIT_FILE" ]] || return 1
  [[ "$(file_digest "$UNIT_FILE")" == "$unit_preimage_digest" ]] || return 1
  unit_is_owned "$UNIT_FILE" || return 1
  local fragment status
  if fragment="$($SYSTEMCTL --user show "$LAUNCHER_NAME" --property=FragmentPath --value 2>/dev/null)"; then
    :
  else
    status=$?
    return "$status"
  fi
  [[ -z "$fragment" || "$fragment" == "$UNIT_FILE" ]]
}

state_matches_preimage() {
  [[ "$state_owned" == "1" && -e "$STATE_FILE" ]] || return 1
  [[ "$(file_digest "$STATE_FILE")" == "$state_preimage_digest" ]]
}

service_active_state=''
service_load_state=''
service_main_pid=''

query_service_state() {
  local status
  if service_active_state="$($SYSTEMCTL --user show "$SERVICE_NAME" --property=ActiveState --value 2>/dev/null)"; then
    :
  else
    status=$?
    return "$status"
  fi
  if service_load_state="$($SYSTEMCTL --user show "$SERVICE_NAME" --property=LoadState --value 2>/dev/null)"; then
    :
  else
    status=$?
    return "$status"
  fi
  if service_main_pid="$($SYSTEMCTL --user show "$SERVICE_NAME" --property=MainPID --value 2>/dev/null)"; then
    :
  else
    status=$?
    return "$status"
  fi
  case "$service_active_state" in active|inactive|failed) ;; *) return 1 ;; esac
  case "$service_load_state" in loaded|not-found) ;; *) return 1 ;; esac
  [[ "$service_main_pid" =~ ^[0-9]+$ ]] || return 1
}

stop_owned_service() {
  query_service_state || return 1
  if [[ "$service_active_state" != "active" ]]; then
    [[ "$service_main_pid" == "0" ]] || return 1
    return 0
  fi
  [[ "$service_load_state" == "loaded" && "$service_main_pid" -gt 1 ]] || return 1
  "$PROCESS_STOP" --pid "$service_main_pid" --repo-root "$REPO_ROOT" --home "$HOME" --port "$PORT" --systemd-unit "$SERVICE_NAME" --systemctl "$SYSTEMCTL" || return 1
  for _ in $(seq 1 50); do
    query_service_state || return 1
    if [[ "$service_active_state" != "active" && "$service_load_state" == "not-found" && "$service_main_pid" == "0" ]]; then
      return 0
    fi
    sleep 0.1
  done
  return 1
}

start_owned_service() {
  "$SERVICE_START" \
    --systemd-run "$SYSTEMD_RUN" \
    --unit "$SERVICE_NAME" \
    --repo-root "$REPO_ROOT" \
    --home "$HOME" \
    --port "$PORT"
}

failed=0
service_result="already absent"
route_result="left unchanged"
unit_removed=0
enable_link_removed=0
previous_active=0
if query_service_state; then
  :
else
  service_query_status=$?
  printf 'ERROR: Could not verify the exact %s ActiveState, LoadState, and MainPID; nothing was changed.\n' "$SERVICE_NAME" >&2
  exit "$service_query_status"
fi
if [[ "$service_active_state" == "active" && "$service_load_state" == "loaded" && "$service_main_pid" -gt 1 ]]; then
  previous_active=1
elif [[ "$service_active_state" != "active" && "$service_main_pid" == "0" ]]; then
  previous_active=0
else
  printf 'ERROR: %s reported an inconsistent lifecycle state; nothing was changed.\n' "$SERVICE_NAME" >&2
  exit 1
fi

restore_service_boundary() {
  local restore_failed=0
  if [[ "$enable_link_removed" == "1" && "$enable_link_owned" == "1" && ! -e "$ENABLE_LINK" && ! -L "$ENABLE_LINK" ]]; then
    if unit_matches_preimage; then
      "$PATH_OP" symlink-create "$UNIT_FILE" "$ENABLE_LINK" \
        --expected-target-digest "$unit_preimage_digest" >/dev/null 2>&1 || restore_failed=1
      [[ "$restore_failed" != "0" ]] || enable_link_removed=0
    else
      restore_failed=1
    fi
  fi
  if [[ "$previous_active" == "1" ]] && unit_matches_preimage; then
    start_owned_service >/dev/null 2>&1 || restore_failed=1
  fi
  return "$restore_failed"
}

if [[ -e "$UNIT_FILE" ]]; then
  if ! unit_matches_preimage; then
    printf 'ERROR: %s changed ownership after preflight; its service, enable link, and unit were preserved.\n' "$SERVICE_NAME" >&2
    failed=1
    service_result="ownership changed"
  elif ! stop_owned_service; then
    printf 'ERROR: Could not stop %s; its enable link and unit were preserved for retry.\n' "$SERVICE_NAME" >&2
    failed=1
    service_result="stop failed"
  elif ! unit_matches_preimage; then
    printf 'ERROR: %s changed ownership while the loaded HermesUI service was stopping; the replacement unit and enable link were preserved.\n' "$SERVICE_NAME" >&2
    failed=1
    service_result="ownership changed after stop"
  elif [[ "$enable_link_owned" == "1" ]] && ! "$PATH_OP" symlink-remove "$ENABLE_LINK" \
    --expected-target "$UNIT_FILE" \
    --expected-target-digest "$unit_preimage_digest"; then
    printf 'ERROR: %s stopped, but its enable link changed ownership and was preserved.\n' "$SERVICE_NAME" >&2
    restore_service_boundary || true
    failed=1
    service_result="enable-link removal failed"
  else
    [[ "$enable_link_owned" != "1" ]] || enable_link_removed=1
    if ! "$PATH_OP" remove "$UNIT_FILE" --expected "$unit_preimage_digest"; then
      printf 'ERROR: %s stopped, but its unit file could not be removed; restoring its prior service state.\n' "$SERVICE_NAME" >&2
      restore_service_boundary || true
      failed=1
      service_result="unit removal failed"
    else
      service_result="removed"
      unit_removed=1
    fi
  fi
else
  if ! query_service_state; then
    printf 'ERROR: %s lifecycle state became unverifiable. It was preserved.\n' "$SERVICE_NAME" >&2
    failed=1
    service_result="state unverifiable"
  elif [[ "$service_active_state" == "active" ]]; then
    printf 'ERROR: %s is active without a verifiable HermesUI-managed unit. It was preserved.\n' "$SERVICE_NAME" >&2
    failed=1
    service_result="active ownership unknown"
  elif [[ "$service_main_pid" != "0" ]]; then
    printf 'ERROR: %s has a nonzero MainPID without a verifiable HermesUI-managed unit. It was preserved.\n' "$SERVICE_NAME" >&2
    failed=1
    service_result="process ownership unknown"
  fi
fi

if [[ "$state_owned" == "1" && ( "$unit_removed" == "1" || "$unit_owned" == "0" ) ]]; then
  if ! "$SYSTEMCTL" --user daemon-reload; then
    printf 'ERROR: systemd user units could not be reloaded.\n' >&2
    failed=1
    service_result="daemon reload failed"
  elif ! load_state="$($SYSTEMCTL --user show "$LAUNCHER_NAME" --property=LoadState --value 2>/dev/null)"; then
    printf 'ERROR: systemd user unit reconciliation could not be verified.\n' >&2
    failed=1
    service_result="daemon reload verification failed"
  elif [[ "$load_state" != "not-found" ]]; then
    printf 'ERROR: %s remains loaded after unit removal; route and ownership state were preserved for retry.\n' "$LAUNCHER_NAME" >&2
    failed=1
    service_result="unit remains loaded"
  fi
fi

if [[ "$failed" == "0" ]]; then
  case "$route_action" in
    remove)
      if ! state_matches_preimage; then
        printf 'ERROR: install.env changed ownership before route cleanup; %s was preserved.\n' "$BASE_PATH" >&2
        failed=1
        route_result="ownership state changed"
      elif ! latest_serve_status="$($TAILSCALE serve status --json 2>/dev/null)"; then
        printf 'ERROR: Tailscale Serve status became unavailable before route cleanup; %s was preserved.\n' "$BASE_PATH" >&2
        failed=1
        route_result="verification unavailable"
      elif [[ "$(inspect_route "$latest_serve_status")" != "owned-top" ]]; then
        printf 'ERROR: %s changed ownership before route cleanup; the current handler was preserved.\n' "$BASE_PATH" >&2
        failed=1
        route_result="ownership changed"
      elif ! serve_cas "$TARGET" absent "$tcp_443_created"; then
        printf 'ERROR: HermesUI cleanup was partial because its %s Serve route could not be removed.\n' "$BASE_PATH" >&2
        failed=1
        route_result="removal failed"
      elif ! post_serve_status="$($TAILSCALE serve status --json 2>/dev/null)"; then
        printf 'ERROR: The Serve removal command succeeded, but the final route state could not be verified.\n' >&2
        failed=1
        route_result="verification unavailable"
      elif [[ "$(inspect_route "$post_serve_status")" != "missing" ]]; then
        printf 'ERROR: The Serve removal command succeeded, but %s is still configured.\n' "$BASE_PATH" >&2
        failed=1
        route_result="verification failed"
      else
        route_result="removed"
      fi
      ;;
    absent) route_result="already absent" ;;
    preserve)
      printf 'WARNING: %s points to another handler, so it was preserved. Inspect: tailscale serve status\n' "$BASE_PATH" >&2
      route_result="foreign handler preserved"
      ;;
  esac
else
  route_result="preserved after service cleanup failure"
fi

if [[ "$failed" == "0" ]]; then
  if [[ "$state_owned" == "1" ]] && ! state_matches_preimage; then
    printf 'ERROR: Runtime cleanup succeeded, but install.env changed ownership and was preserved.\n' >&2
    failed=1
  elif ! "$PATH_OP" remove "$STATE_FILE" --expected "$state_preimage_digest"; then
    printf 'ERROR: Runtime cleanup succeeded, but the HermesUI install state could not be removed.\n' >&2
    failed=1
  else
    rmdir "$STATE_DIR" >/dev/null 2>&1 || true
  fi
fi

if [[ "$failed" != "0" ]]; then
  printf 'ERROR: HermesUI uninstall incomplete. Service: %s; Tailnet route: %s. Install state was preserved for retry.\n' "$service_result" "$route_result" >&2
  exit 1
fi
printf 'HermesUI uninstall complete. Service: %s; Tailnet route: %s. Hermes data and the repository were preserved.\n' "$service_result" "$route_result"
