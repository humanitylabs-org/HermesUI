#!/usr/bin/env bash
set -euo pipefail

INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${HERMESUI_REPO_ROOT_OVERRIDE:-$(cd "$INSTALLER_DIR/../.." && pwd)}"
[[ "$REPO_ROOT" == /* ]] || { printf 'ERROR: HermesUI repository root must be absolute.\n' >&2; exit 1; }
PORT="${HERMESUI_PORT:-}"
HOST="127.0.0.1"
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
SYSTEMD_ANALYZE="${HERMESUI_SYSTEMD_ANALYZE:-systemd-analyze}"
TAILSCALE="${HERMESUI_TAILSCALE:-tailscale}"
CURL="${HERMESUI_CURL:-curl}"
PATH_OP="${HERMESUI_PATH_OP:-${INSTALLER_DIR}/owned-path-op.py}"
SERVE_CAS="${HERMESUI_SERVE_CAS_HELPER:-${INSTALLER_DIR}/tailscale-serve-cas.py}"
PROCESS_STOP="${HERMESUI_PROCESS_STOP:-${INSTALLER_DIR}/stop-owned-process.py}"
SERVICE_START="${HERMESUI_SERVICE_START:-${INSTALLER_DIR}/systemd-start-owned.py}"
LAUNCHER_UNIT="${HERMESUI_LAUNCHER_UNIT_HELPER:-${INSTALLER_DIR}/systemd-launcher-unit.py}"
RUNTIME_GUARD="${HERMESUI_RUNTIME_HOME_GUARD:-${INSTALLER_DIR}/runtime-home-guard.py}"
LOCK_HELPER="${HERMESUI_LIFECYCLE_LOCK_HELPER:-${INSTALLER_DIR}/acquire-lifecycle-lock.py}"
SYSTEMD_RUN="${HERMESUI_SYSTEMD_RUN:-systemd-run}"
LIFECYCLE_LOCK="${HERMESUI_LIFECYCLE_LOCK_FILE:-${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/hermesui-${UID}/lifecycle.lock}"

acquire_lifecycle_lock() {
  if [[ "${HERMESUI_LIFECYCLE_LOCK_HELD:-0}" == "1" ]]; then
    python3 "$LOCK_HELPER" --lock "$LIFECYCLE_LOCK" --fd 9 --verify-inherited || exit 75
  else
    exec python3 "$LOCK_HELPER" --lock "$LIFECYCLE_LOCK" --fd 9 -- "$INSTALLER_DIR/tailnet-setup.sh" "$@"
  fi
}

acquire_lifecycle_lock "$@"

requested_mode="${HERMESUI_MODE:-standalone}"
case "$requested_mode" in
  standalone) ;;
  external)
    printf 'ERROR: HermesUI external/client-only mode is not supported safely in v0.2.2 because the current backend protocol cannot prove runtime-home and profile identity. Nothing was changed.\n' >&2
    exit 1
    ;;
  isolated)
    printf 'ERROR: HermesUI isolated mode is not yet supported. Nothing was changed.\n' >&2
    exit 1
    ;;
  *)
    printf 'ERROR: HERMESUI_MODE must be standalone. Nothing was changed.\n' >&2
    exit 1
    ;;
esac

RUNTIME_COMMIT="$(git -C "$REPO_ROOT" rev-parse --verify HEAD 2>/dev/null)" || runtime_identity_failed=1
RUNTIME_TREE="$(git -C "$REPO_ROOT" rev-parse --verify 'HEAD^{tree}' 2>/dev/null)" || runtime_identity_failed=1
if [[ "${runtime_identity_failed:-0}" != "0" || ! "$RUNTIME_COMMIT" =~ ^[0-9a-f]{40}$ || ! "$RUNTIME_TREE" =~ ^[0-9a-f]{40}$ ]]; then
  printf 'ERROR: Could not resolve the exact HermesUI Git commit/tree runtime identity.\n' >&2
  exit 1
fi

transaction_started=0
install_complete=0
route_mutated=0
route_apply_confirmed=0
state_mutated=0
unit_mutated=0
service_mutated=0
enable_link_created=0
txn_dir=''
state_tmp=''
unit_candidate=''
state_backup=''
unit_backup=''
rollback_failed=0
runtime_restore_deferred=0
state_file_existed=0
unit_file_existed=0
previous_enabled=0
previous_active=0
existing_route_proxy=''
installed_route_proxy=''
state_preimage_digest=''
unit_preimage_digest=''
state_installed_digest=''
unit_installed_digest=''
tcp_443_created=''
unit_schema=current
requested_hermes_home="${HERMES_HOME:-}"
requested_profile="${HERMES_PROFILE:-default}"
[[ "$requested_profile" == "default" ]] || {
  printf 'ERROR: HermesUI v0.2.2 standalone installation supports only the default Hermes profile.\n' >&2
  exit 1
}
default_hermes_home="$(python3 "$RUNTIME_GUARD" normalize "$HOME/.hermes")" || exit 1
if [[ -n "$requested_hermes_home" ]]; then
  requested_hermes_home="$(python3 "$RUNTIME_GUARD" normalize "$requested_hermes_home")" || exit 1
fi
RESOLVED_HERMES_HOME="${requested_hermes_home:-$default_hermes_home}"
RESOLVED_PROFILE=default

state_owned=0
if [[ -e "$STATE_FILE" ]]; then
  if [[ ! -r "$STATE_FILE" ]]; then
    printf 'ERROR: HermesUI install state is unreadable; refusing an ownership-ambiguous setup.\n' >&2
    exit 1
  fi
  saved_port=''
  saved_tcp_443_created=''
  saved_state_version=''
  saved_mode=''
  saved_hermes_home=''
  saved_profile=''
  state_invalid=0
  while IFS='=' read -r key value; do
    case "$key" in
      HERMESUI_PORT)
        if [[ -n "$saved_port" ]]; then state_invalid=1; else saved_port="$value"; fi
        ;;
      HERMESUI_TCP_443_CREATED)
        if [[ -n "$saved_tcp_443_created" ]]; then state_invalid=1; else saved_tcp_443_created="$value"; fi
        ;;
      HERMESUI_STATE_VERSION)
        if [[ -n "$saved_state_version" ]]; then state_invalid=1; else saved_state_version="$value"; fi
        ;;
      HERMESUI_MODE)
        if [[ -n "$saved_mode" ]]; then state_invalid=1; else saved_mode="$value"; fi
        ;;
      HERMESUI_HERMES_HOME)
        if [[ -n "$saved_hermes_home" ]]; then state_invalid=1; else saved_hermes_home="$value"; fi
        ;;
      HERMESUI_PROFILE)
        if [[ -n "$saved_profile" ]]; then state_invalid=1; else saved_profile="$value"; fi
        ;;
      *) state_invalid=1 ;;
    esac
  done <"$STATE_FILE"
  if [[ -z "$saved_state_version$saved_mode$saved_hermes_home$saved_profile" ]]; then
    unit_schema=legacy
    saved_hermes_home="$default_hermes_home"
    saved_profile=default
  elif [[ "$saved_state_version" != "2" || "$saved_mode" != "standalone" || "$saved_profile" != "default" ]]; then
    state_invalid=1
  else
    saved_hermes_home="$(python3 "$RUNTIME_GUARD" normalize "$saved_hermes_home")" || state_invalid=1
  fi
  if [[ "$state_invalid" != "0" || ! "$saved_port" =~ ^[0-9]+$ || ! "$saved_tcp_443_created" =~ ^[01]$ ]]; then
    printf 'ERROR: HermesUI install state is invalid; refusing to replace the persisted port with a default.\n' >&2
    exit 1
  fi
  if [[ -n "$PORT" && "$PORT" != "$saved_port" ]]; then
    printf 'ERROR: HERMESUI_PORT does not match the installer-owned port in install.env. Nothing was changed.\n' >&2
    exit 1
  fi
  if [[ -n "$requested_hermes_home" && "$requested_hermes_home" != "$saved_hermes_home" ]]; then
    printf 'ERROR: HERMES_HOME does not match the installer-owned runtime home in install.env. Nothing was changed.\n' >&2
    exit 1
  fi
  PORT="$saved_port"
  tcp_443_created="$saved_tcp_443_created"
  RESOLVED_HERMES_HOME="$saved_hermes_home"
  RESOLVED_PROFILE="$saved_profile"
  state_owned=1
  state_preimage_digest="$("$PATH_OP" digest "$STATE_FILE")" || exit 1
fi
PORT="${PORT:-8793}"

fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }
ok() { printf 'OK: %s\n' "$1"; }

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

rollback_on_exit() {
  status=$?
  trap - EXIT
  if [[ "$transaction_started" == "1" && "$install_complete" != "1" ]]; then
    set +e
    rollback_failed=0
    printf 'ERROR: setup failed; rolling back HermesUI changes.\n' >&2

    if [[ "$route_mutated" == "1" ]]; then
      restore_route=0
      if ! current_serve_status="$($TAILSCALE serve status --json 2>/dev/null)"; then
        printf 'ERROR: the HermesUI Serve route ownership could not be verified during rollback; it was preserved.\n' >&2
        rollback_failed=1
      elif [[ "$route_apply_confirmed" == "1" ]]; then
        if route_matches_proxy "$current_serve_status" "$installed_route_proxy"; then
          restore_route=1
        else
          printf 'ERROR: the HermesUI Serve route changed ownership during setup; it was preserved.\n' >&2
          rollback_failed=1
        fi
      elif route_matches_proxy "$current_serve_status" "$existing_route_proxy"; then
        : # The failed Serve command left the exact prior route state unchanged.
      elif route_matches_proxy "$current_serve_status" "http://${HOST}:${PORT}" || route_matches_proxy "$current_serve_status" "http://${HOST}:${PORT}${BASE_PATH}"; then
        restore_route=1 # The failed Serve command partially installed our intended route.
      else
        printf 'ERROR: the HermesUI Serve route changed ownership during setup; it was preserved.\n' >&2
        rollback_failed=1
      fi
      if [[ "$restore_route" == "1" ]]; then
        rollback_route_expected="$existing_route_proxy"
        if serve_cas "${installed_route_proxy:-http://${HOST}:${PORT}}" "${existing_route_proxy:-absent}" "$tcp_443_created" >/dev/null 2>&1; then
          :
        elif [[ -n "$existing_route_proxy" ]] && serve_cas "${installed_route_proxy:-http://${HOST}:${PORT}}" absent "$tcp_443_created" >/dev/null 2>&1; then
          # A Funnel-safe CAS refuses to restore a non-absent route if Funnel
          # appeared after setup. Remove our still-owned candidate route instead.
          rollback_route_expected=''
          rollback_failed=1
          printf 'ERROR: the prior HermesUI Tailnet route %s could not be restored because Funnel is enabled; the candidate route was removed. Disable Funnel and rerun setup to restore the managed route.\n' "$existing_route_proxy" >&2
        else
          rollback_failed=1
        fi
        if ! current_serve_status="$($TAILSCALE serve status --json 2>/dev/null)" || ! route_matches_proxy "$current_serve_status" "$rollback_route_expected"; then
          rollback_failed=1
        fi
      fi
    fi

    unit_still_owned=1
    if [[ "$unit_mutated" == "1" ]]; then
      current_fragment=''
      if ! current_fragment="$($SYSTEMCTL --user show "$LAUNCHER_NAME" --property=FragmentPath --value 2>/dev/null)"; then
        printf 'ERROR: the HermesUI systemd unit provenance could not be verified during rollback; the unit and service were preserved.\n' >&2
        unit_still_owned=0
        rollback_failed=1
      elif [[ ! -f "$UNIT_FILE" ]] || ! cmp -s "$txn_dir/unit.installed" "$UNIT_FILE" || { [[ "$service_mutated" == "1" ]] && [[ "$current_fragment" != "$UNIT_FILE" ]]; }; then
        printf 'ERROR: the HermesUI launcher changed ownership during setup; the foreign launcher was preserved.\n' >&2
        unit_still_owned=0
        rollback_failed=1
      fi
    fi
    service_stopped=1
    if [[ "$service_mutated" == "1" ]]; then
      if ! stop_owned_service "$RUNTIME_COMMIT:$RUNTIME_TREE" >/dev/null 2>&1; then
        service_stopped=0
        rollback_failed=1
        printf 'ERROR: the HermesUI runtime state could not be queried or stopped authoritatively during rollback; its unit, enable link, and install state were preserved.\n' >&2
      fi
    fi
    if [[ "$enable_link_created" == "1" && "$unit_still_owned" == "1" && "$service_stopped" == "1" ]]; then
      "$PATH_OP" symlink-remove "$ENABLE_LINK" \
        --expected-target "$UNIT_FILE" \
        --expected-target-digest "$unit_installed_digest" || rollback_failed=1
    elif [[ "$enable_link_created" == "1" && "$service_stopped" != "1" ]]; then
      printf 'ERROR: the HermesUI enable link was preserved because the runtime could not be stopped authoritatively.\n' >&2
    elif [[ "$enable_link_created" == "1" ]]; then
      printf 'ERROR: the HermesUI enable link now resolves through a foreign unit and was preserved.\n' >&2
      rollback_failed=1
    fi
    if [[ "$unit_mutated" == "1" && "$unit_still_owned" == "1" && "$service_stopped" == "1" ]]; then
      if [[ "$unit_file_existed" == "1" ]]; then
        "$PATH_OP" publish "$unit_backup" "$UNIT_FILE" --expected "$unit_installed_digest" || rollback_failed=1
      else
        "$PATH_OP" remove "$UNIT_FILE" --expected "$unit_installed_digest" || rollback_failed=1
      fi
    fi
    if [[ "$state_mutated" == "1" && "$service_stopped" == "1" ]]; then
      if [[ ! -f "$STATE_FILE" ]] || ! cmp -s "$txn_dir/state.installed" "$STATE_FILE"; then
        printf 'ERROR: HermesUI install.env changed ownership during setup; it was preserved.\n' >&2
        rollback_failed=1
      elif [[ "$state_file_existed" == "1" ]]; then
        "$PATH_OP" publish "$state_backup" "$STATE_FILE" --expected "$state_installed_digest" || rollback_failed=1
      else
        "$PATH_OP" remove "$STATE_FILE" --expected "$state_installed_digest" || rollback_failed=1
      fi
    elif [[ "$state_mutated" == "1" ]]; then
      printf 'ERROR: install.env was preserved because the runtime could not be stopped authoritatively.\n' >&2
    fi
    if [[ "$unit_mutated" == "1" && "$unit_still_owned" == "1" && "$service_stopped" == "1" ]]; then
      "$SYSTEMCTL" --user daemon-reload >/dev/null 2>&1 || rollback_failed=1
    fi

    if [[ "$service_mutated" == "1" && "$unit_owned" == "1" && "$unit_still_owned" == "1" && "$service_stopped" == "1" ]]; then
      if [[ "$previous_active" == "1" ]]; then
        if [[ "${HERMESUI_DEFER_SERVICE_RESTORE:-0}" == "1" ]]; then
          runtime_restore_deferred=1
        else
          start_owned_service >/dev/null 2>&1 || rollback_failed=1
        fi
      else
        stop_owned_service "$RUNTIME_COMMIT:$RUNTIME_TREE" >/dev/null 2>&1 || rollback_failed=1
      fi
    fi
    [[ -z "$state_tmp" ]] || rm -f "$state_tmp"
    [[ -z "$unit_candidate" ]] || rm -f "$unit_candidate"

    if [[ "$rollback_failed" == "0" && "$runtime_restore_deferred" == "1" ]]; then
      printf 'OK: local setup artifacts were rolled back; runtime restoration is deferred to the locked updater.\n' >&2
    elif [[ "$rollback_failed" == "0" ]]; then
      printf 'OK: failed setup changes were rolled back.\n' >&2
    else
      printf 'ERROR: automatic rollback was incomplete; inspect the HermesUI unit, install.env, and Tailscale Serve route.\n' >&2
    fi
  fi
  if [[ "$install_complete" == "1" || "$rollback_failed" == "0" ]]; then
    [[ -z "$state_backup" ]] || rm -f "$state_backup"
    [[ -z "$unit_backup" ]] || rm -f "$unit_backup"
    [[ -z "$txn_dir" ]] || rm -rf "$txn_dir"
  else
    printf 'ERROR: rollback evidence was preserved at %s, %s, and %s.\n' \
      "${state_backup:-<none>}" "${unit_backup:-<none>}" "${txn_dir:-<none>}" >&2
  fi
  exit "$status"
}

unit_is_owned() {
  local -a schema_args
  if [[ "$unit_schema" == "legacy" ]]; then
    schema_args=(--legacy)
  else
    schema_args=(--hermes-home "$RESOLVED_HERMES_HOME" --profile "$RESOLVED_PROFILE")
  fi
  "$LAUNCHER_UNIT" verify "$1" \
    --repo-root "$REPO_ROOT" \
    --home "$HOME" \
    --host "$HOST" \
    --port "$PORT" \
    "${schema_args[@]}"
}

published_unit_matches() {
  [[ -f "$UNIT_FILE" ]] || return 1
  [[ "$("$PATH_OP" digest "$UNIT_FILE")" == "$unit_installed_digest" ]] || return 1
  unit_is_owned "$UNIT_FILE"
}

loaded_unit_matches() {
  local fragment status
  if fragment="$($SYSTEMCTL --user show "$LAUNCHER_NAME" --property=FragmentPath --value 2>/dev/null)"; then
    :
  else
    status=$?
    return "$status"
  fi
  [[ "$fragment" == "$UNIT_FILE" ]] || return 1
  published_unit_matches
}

service_active_state=''
service_load_state=''
service_main_pid=''

query_service_state() {
  local raw parsed status
  if raw="$($SYSTEMCTL --user show "$SERVICE_NAME" \
    --property=ActiveState --property=LoadState --property=MainPID 2>/dev/null)"; then
    :
  else
    status=$?
    return "$status"
  fi
  parsed="$(python3 - "$raw" <<'PY'
import sys

properties = {}
for line in sys.argv[1].splitlines():
    if '=' not in line:
        raise SystemExit(1)
    key, value = line.split('=', 1)
    if key in properties:
        raise SystemExit(1)
    properties[key] = value
if set(properties) != {'ActiveState', 'LoadState', 'MainPID'}:
    raise SystemExit(1)
if properties['ActiveState'] not in {'active', 'inactive', 'failed'}:
    raise SystemExit(1)
if properties['LoadState'] not in {'loaded', 'not-found'}:
    raise SystemExit(1)
try:
    pid = int(properties['MainPID'])
except ValueError:
    raise SystemExit(1)
if pid < 0:
    raise SystemExit(1)
active = properties['ActiveState']
load = properties['LoadState']
if active == 'active':
    if load != 'loaded' or pid <= 1:
        raise SystemExit(1)
elif pid != 0:
    raise SystemExit(1)
print(properties['ActiveState'], properties['LoadState'], pid, sep='\t')
PY
)" || return 1
  IFS=$'\t' read -r service_active_state service_load_state service_main_pid <<<"$parsed"
}

stop_owned_service() {
  local identity
  local -a identity_args=() runtime_args=()
  query_service_state || return 1
  if [[ "$service_active_state" != "active" ]]; then
    [[ "$service_main_pid" == "0" ]] || return 1
    return 0
  fi
  [[ "$service_load_state" == "loaded" && "$service_main_pid" -gt 1 ]] || return 1
  for identity in "$@"; do
    identity_args+=(--runtime-identity "$identity")
  done
  if [[ "$unit_schema" == "current" ]]; then
    runtime_args=(--hermes-home "$RESOLVED_HERMES_HOME" --profile "$RESOLVED_PROFILE")
  fi
  "$PROCESS_STOP" --pid "$service_main_pid" --repo-root "$REPO_ROOT" --home "$HOME" --port "$PORT" --systemd-unit "$SERVICE_NAME" --systemctl "$SYSTEMCTL" "${runtime_args[@]}" "${identity_args[@]}" || return 1
  for _ in $(seq 1 50); do
    query_service_state || return 1
    if [[ "$service_active_state" == "inactive" && "$service_load_state" == "not-found" && "$service_main_pid" == "0" ]]; then
      return 0
    fi
    sleep 0.1
  done
  return 1
}

verify_owned_service_pid() {
  local main_pid="$1" identity
  shift
  local -a identity_args=() runtime_args=()
  [[ "$main_pid" =~ ^[0-9]+$ && "$main_pid" -gt 1 ]] || return 1
  if [[ "$#" == "0" ]]; then
    set -- "$RUNTIME_COMMIT:$RUNTIME_TREE"
  fi
  for identity in "$@"; do
    identity_args+=(--runtime-identity "$identity")
  done
  if [[ "$unit_schema" == "current" ]]; then
    runtime_args=(--hermes-home "$RESOLVED_HERMES_HOME" --profile "$RESOLVED_PROFILE")
  fi
  "$PROCESS_STOP" --pid "$main_pid" --repo-root "$REPO_ROOT" --home "$HOME" --port "$PORT" --systemd-unit "$SERVICE_NAME" --systemctl "$SYSTEMCTL" "${runtime_args[@]}" "${identity_args[@]}" --verify-only
}

start_owned_service() {
  "$SERVICE_START" \
    --systemd-run "$SYSTEMD_RUN" \
    --unit "$SERVICE_NAME" \
    --repo-root "$REPO_ROOT" \
    --home "$HOME" \
    --hermes-home "$RESOLVED_HERMES_HOME" \
    --profile "$RESOLVED_PROFILE" \
    --port "$PORT"
}

assert_no_funnel() {
  python3 - "$1" <<'PY'
import json, sys
try:
    root = json.loads(sys.argv[1])
except Exception as exc:
    raise SystemExit(f'ERROR: invalid Tailscale Serve status JSON: {exc}')

def configs(config):
    if not isinstance(config, dict):
        return
    yield config
    for nested in (config.get('Foreground') or {}).values():
        yield from configs(nested)

for config in configs(root):
    if any(value is True for value in (config.get('AllowFunnel') or {}).values()):
        raise SystemExit('ERROR: Tailscale Funnel is enabled. Disable Funnel before installing HermesUI.')
PY
}

assert_route_safe() {
  python3 - "$BASE_PATH" "http://${HOST}:${PORT}" "$1" "$2" "$3" "$CANONICAL_LISTENER" <<'PY'
import json, sys
path, target, raw, mode, ownership, canonical_listener = sys.argv[1:]
try:
    config = json.loads(raw)
except Exception as exc:
    raise SystemExit(f'ERROR: invalid Tailscale Serve status JSON: {exc}')
allowed = {target.rstrip('/'), target.rstrip('/') + path}
matches = []

def configs(value, provenance='top'):
    if not isinstance(value, dict):
        raise SystemExit('ERROR: Tailscale Serve configuration is invalid. Nothing was changed.')
    yield value, provenance
    if 'Foreground' not in value:
        return
    foreground = value['Foreground']
    if not isinstance(foreground, dict):
        raise SystemExit('ERROR: Tailscale Serve Foreground configuration is invalid. Nothing was changed.')
    for nested in foreground.values():
        yield from configs(nested, 'foreground')

for value, provenance in configs(config):
    if 'Web' not in value:
        continue
    web_configs = value['Web']
    if not isinstance(web_configs, dict):
        raise SystemExit('ERROR: Tailscale Serve Web configuration is invalid. Nothing was changed.')
    if canonical_listener not in web_configs:
        continue
    web = web_configs[canonical_listener]
    if not isinstance(web, dict):
        raise SystemExit('ERROR: Tailscale Serve listener configuration is invalid. Nothing was changed.')
    if 'Handlers' not in web:
        continue
    handlers = web['Handlers']
    if not isinstance(handlers, dict):
        raise SystemExit('ERROR: Tailscale Serve Handlers configuration is invalid. Nothing was changed.')
    if path not in handlers:
        continue
    handler = handlers[path]
    if not isinstance(handler, dict) or set(handler) != {'Proxy'}:
        raise SystemExit('ERROR: Tailscale Serve path /hermesUI has a non-Proxy handler. Nothing was changed.')
    proxy = str(handler['Proxy'] or '').rstrip('/')
    matches.append((provenance, proxy))

if any(proxy not in allowed for _, proxy in matches):
    raise SystemExit('ERROR: Tailscale Serve path /hermesUI already belongs to a different handler. Remove or relocate it explicitly before installing.')
if any(provenance == 'foreground' for provenance, _ in matches):
    raise SystemExit('ERROR: Tailscale Serve path /hermesUI has a Foreground or mixed handler that a background install cannot safely own. Remove it explicitly before installing.')
if len(matches) > 1:
    raise SystemExit('ERROR: Tailscale Serve path /hermesUI has multiple top-level handlers. Remove the ambiguity explicitly before installing.')
if mode == 'optional' and matches and ownership != 'verified':
    raise SystemExit('ERROR: Tailscale Serve path /hermesUI matches HermesUI but has no complete installer ownership state. It may be a manual route, so nothing was changed.')
if mode == 'required' and not matches:
    raise SystemExit('ERROR: Tailscale Serve did not publish the /hermesUI route.')
if matches:
    print(matches[0][1])
PY
}

route_matches_proxy() {
  python3 - "$BASE_PATH" "$1" "$2" "$CANONICAL_LISTENER" <<'PY'
import json, sys
path, raw, expected, canonical_listener = sys.argv[1:]
try:
    config = json.loads(raw)
except Exception:
    raise SystemExit(1)
matches = []

def configs(value, provenance='top'):
    if not isinstance(value, dict):
        raise SystemExit(1)
    yield value, provenance
    if 'Foreground' not in value:
        return
    foreground = value['Foreground']
    if not isinstance(foreground, dict):
        raise SystemExit(1)
    for nested in foreground.values():
        yield from configs(nested, 'foreground')

for value, provenance in configs(config):
    if 'Web' not in value:
        continue
    web_configs = value['Web']
    if not isinstance(web_configs, dict):
        raise SystemExit(1)
    if canonical_listener not in web_configs:
        continue
    web = web_configs[canonical_listener]
    if not isinstance(web, dict):
        raise SystemExit(1)
    if 'Handlers' not in web:
        continue
    handlers = web['Handlers']
    if not isinstance(handlers, dict):
        raise SystemExit(1)
    if path not in handlers:
        continue
    handler = handlers[path]
    if not isinstance(handler, dict) or set(handler) != {'Proxy'}:
        raise SystemExit(1)
    matches.append((provenance, str(handler['Proxy'] or '').rstrip('/')))
if any(provenance != 'top' for provenance, _ in matches) or len(matches) > 1:
    raise SystemExit(1)
actual = matches[0][1] if matches else ''
raise SystemExit(0 if actual == expected.rstrip('/') else 1)
PY
}

if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1024 || PORT > 65535 )); then
  fail "HERMESUI_PORT must be an unprivileged TCP port from 1024 through 65535."
fi
[[ "$REPO_ROOT" != *$'\n'* && "$HOME" != *$'\n'* ]] || fail "Paths containing newlines are unsupported."

runtime_operation="${HERMESUI_RUNTIME_OPERATION:-}"
if [[ -n "$runtime_operation" ]]; then
  expected_runtime_commit="${HERMESUI_EXPECTED_RUNTIME_COMMIT:-}"
  expected_runtime_tree="${HERMESUI_EXPECTED_RUNTIME_TREE:-}"
  [[ "$runtime_operation" =~ ^(probe|stop|ensure-active|ensure-inactive)$ ]] || fail "Unknown locked runtime-only operation."
  [[ "$expected_runtime_commit" =~ ^[0-9a-f]{40}$ && "$expected_runtime_tree" =~ ^[0-9a-f]{40}$ ]] || fail "Runtime-only operation requires exact expected commit and tree identities."
  [[ "$RUNTIME_COMMIT" == "$expected_runtime_commit" && "$RUNTIME_TREE" == "$expected_runtime_tree" ]] || fail "Runtime-only operation checkout identity does not match the expected commit/tree."
  [[ "$state_owned" == "1" && -f "$UNIT_FILE" ]] || fail "Runtime-only operation requires complete HermesUI install state and launcher ownership."
  unit_is_owned "$UNIT_FILE" || fail "Runtime-only operation refused launcher bytes not owned by the expected checkout."
  runtime_fragment="$($SYSTEMCTL --user show "$LAUNCHER_NAME" --property=FragmentPath --value 2>/dev/null)" || fail "Runtime-only operation could not verify launcher FragmentPath."
  [[ "$runtime_fragment" == "$UNIT_FILE" ]] || fail "Runtime-only operation found a foreign launcher FragmentPath."
  query_service_state || fail "Runtime-only operation could not obtain a stable ActiveState/LoadState/MainPID tuple."
  if [[ "$service_active_state" == "active" ]]; then
    verify_owned_service_pid "$service_main_pid" "$expected_runtime_commit:$expected_runtime_tree" || fail "Runtime-only operation found a running process with the wrong commit/tree identity."
    runtime_was_active=1
  else
    runtime_was_active=0
  fi
  case "$runtime_operation" in
    probe)
      if [[ "$runtime_was_active" == "1" ]]; then printf 'active\n'; else printf 'inactive\n'; fi
      ;;
    stop|ensure-inactive)
      if [[ "$runtime_was_active" == "1" ]]; then
        "$RUNTIME_GUARD" check --hermes-home "$RESOLVED_HERMES_HOME" --allow-pid "$service_main_pid" || \
          fail "Runtime-only operation found another or ambiguous execution backend using the managed Hermes home. Nothing was stopped."
        stop_owned_service "$expected_runtime_commit:$expected_runtime_tree" || fail "Runtime-only operation could not stop the exact managed runtime safely."
      fi
      printf 'inactive\n'
      ;;
    ensure-active)
      if [[ "$runtime_was_active" != "1" ]]; then
        start_owned_service || fail "Runtime-only operation could not start the exact managed runtime."
        query_service_state || fail "Runtime-only operation could not verify the started runtime state."
        [[ "$service_active_state" == "active" && "$service_load_state" == "loaded" && "$service_main_pid" -gt 1 ]] || fail "Runtime-only operation did not reach a stable active state."
        verify_owned_service_pid "$service_main_pid" "$expected_runtime_commit:$expected_runtime_tree" || fail "Runtime-only operation started a process with the wrong commit/tree identity."
      fi
      printf 'active\n'
      ;;
  esac
  exit 0
fi

if [[ "${HERMESUI_SKIP_PREREQS:-0}" != "1" ]]; then
  "$INSTALLER_DIR/tailnet-prereq-check.sh"
fi
dns_name="$($TAILSCALE status --self --json 2>/dev/null | python3 -c 'import json,sys; print(((json.load(sys.stdin).get("Self") or {}).get("DNSName") or "").rstrip("."))')"
[[ "$dns_name" == *.ts.net ]] || fail "Could not determine this device's Tailscale MagicDNS name."
CANONICAL_LISTENER="${dns_name}:443"

unit_owned=0
if existing_fragment="$($SYSTEMCTL --user show "$LAUNCHER_NAME" --property=FragmentPath --value 2>/dev/null)"; then
  :
else
  fragment_status=$?
  printf 'ERROR: Could not verify the systemd provenance of %s. Nothing was changed.\n' "$LAUNCHER_NAME" >&2
  exit "$fragment_status"
fi
[[ "$existing_fragment" != *$'\n'* ]] || fail "The existing systemd unit path is invalid."
for candidate in "$UNIT_FILE" "$existing_fragment"; do
  [[ -n "$candidate" && -e "$candidate" ]] || continue
  unit_is_owned "$candidate" || fail "$LAUNCHER_NAME already exists but is not managed by HermesUI. Remove or rename it explicitly before installing."
  unit_owned=1
done
if [[ -e "$UNIT_FILE" ]]; then
  unit_preimage_digest="$("$PATH_OP" digest "$UNIT_FILE")" || exit 1
fi
if [[ "$unit_owned" == "1" && "$state_owned" != "1" ]]; then
  fail "$LAUNCHER_NAME is managed by HermesUI, but install.env is missing. The port and route ownership cannot be verified, so nothing was changed."
fi

managed_running=0
if ! query_service_state; then
  fail "Could not verify the exact $SERVICE_NAME ActiveState, LoadState, and MainPID. Nothing was changed."
elif [[ "$service_active_state" == "active" ]]; then
  [[ "$service_load_state" == "loaded" && "$service_main_pid" -gt 1 ]] || fail "$SERVICE_NAME reported an inconsistent active state. Nothing was changed."
  [[ "$unit_owned" == "1" ]] || fail "$SERVICE_NAME is active but its launcher ownership cannot be verified. Stop and inspect it before installing."
  verify_owned_service_pid "$service_main_pid" || fail "$SERVICE_NAME is active but its process identity is not managed by this HermesUI checkout."
  managed_running=1
elif [[ "$service_main_pid" != "0" ]]; then
  fail "$SERVICE_NAME reported a nonzero MainPID while inactive. Nothing was changed."
fi

guard_args=(--hermes-home "$RESOLVED_HERMES_HOME")
if [[ "$managed_running" == "1" ]]; then
  guard_args+=(--allow-pid "$service_main_pid")
fi
python3 "$RUNTIME_GUARD" check "${guard_args[@]}" || exit 1

port_busy="$(python3 - "$HOST" "$PORT" <<'PY'
import socket, sys
sock = socket.socket()
sock.settimeout(0.25)
try:
    busy = sock.connect_ex((sys.argv[1], int(sys.argv[2]))) == 0
finally:
    sock.close()
print('1' if busy else '0')
PY
)"
if [[ "$port_busy" == "1" ]]; then
  [[ "$managed_running" == "1" ]] || fail "Port $PORT is already in use by a process not managed by $SERVICE_NAME. Nothing was changed."
  current_manifest="$($CURL -fsS --max-time 5 "http://${HOST}:${PORT}/manifest.json" 2>/dev/null || true)"
  python3 - "$current_manifest" <<'PY' || fail "Port is used by $SERVICE_NAME, but its manifest is not HermesUI. Stop and inspect the service before continuing."
import json, sys
try:
    manifest = json.loads(sys.argv[1])
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if manifest.get('name') == 'HermesUI' else 1)
PY
fi

serve_status="$($TAILSCALE serve status --json 2>/dev/null)" || fail "Could not inspect the existing Tailscale Serve configuration."
assert_no_funnel "$serve_status" || exit 1
if [[ "$state_owned" != "1" ]]; then
  tcp_443_state="$(python3 - "$serve_status" <<'PY'
import json, sys
config = json.loads(sys.argv[1])
if "TCP" not in config:
    print("absent")
    raise SystemExit(0)
tcp = config["TCP"]
if not isinstance(tcp, dict):
    raise SystemExit("ERROR: TCP Serve configuration is invalid; refusing to mutate it.")
if "443" not in tcp:
    print("absent")
elif tcp["443"] == {"HTTPS": True}:
    print("owned")
else:
    raise SystemExit("ERROR: TCP 443 has incompatible Serve configuration; refusing to mutate it.")
PY
)" || fail "Could not establish safe TCP 443 ownership from the current Serve configuration."
  if [[ "$tcp_443_state" == "owned" ]]; then
    tcp_443_created=0
  elif [[ "$tcp_443_state" == "absent" ]]; then
    tcp_443_created=1
  else
    fail "Could not establish safe TCP 443 ownership from the current Serve configuration."
  fi
fi
route_ownership="unverified"
if [[ "$state_owned" == "1" && "$unit_owned" == "1" ]]; then
  route_ownership="verified"
fi
existing_route_proxy="$(assert_route_safe "$serve_status" optional "$route_ownership")" || exit 1

txn_dir="$(mktemp -d "${TMPDIR:-/tmp}/hermesui-setup.XXXXXX")" || fail "Could not create a rollback workspace."
trap rollback_on_exit EXIT
if [[ -e "$STATE_FILE" ]]; then
  state_backup="$(mktemp "${STATE_DIR}/.install.env.rollback.XXXXXX")" || fail "Could not reserve install.env rollback storage."
  cp -p "$STATE_FILE" "$state_backup" || fail "Could not back up install.env before setup."
  state_file_existed=1
fi
if [[ -e "$UNIT_FILE" ]]; then
  unit_backup="$(mktemp "${SYSTEMD_DIR}/.${LAUNCHER_NAME}.rollback.XXXXXX")" || fail "Could not reserve systemd unit rollback storage."
  cp -p "$UNIT_FILE" "$unit_backup" || fail "Could not back up the systemd unit before setup."
  unit_file_existed=1
fi
if [[ -L "$ENABLE_LINK" ]]; then
  [[ "$("$PATH_OP" readlink "$ENABLE_LINK")" == "$UNIT_FILE" ]] || fail "The default.target enable link for $LAUNCHER_NAME is foreign. Nothing was changed."
  previous_enabled=1
elif [[ -e "$ENABLE_LINK" ]]; then
  fail "The default.target enable path for $LAUNCHER_NAME is not a HermesUI-managed symlink. Nothing was changed."
fi
previous_active="$managed_running"
transaction_started=1

mkdir -p "$STATE_DIR"
state_tmp="$(mktemp "${STATE_DIR}/.install.env.candidate.XXXXXX")" || fail "Could not create install state candidate."
printf 'HERMESUI_STATE_VERSION=2\nHERMESUI_MODE=standalone\nHERMESUI_HERMES_HOME=%s\nHERMESUI_PROFILE=%s\nHERMESUI_PORT=%s\nHERMESUI_TCP_443_CREATED=%s\n' \
  "$RESOLVED_HERMES_HOME" "$RESOLVED_PROFILE" "$PORT" "$tcp_443_created" >"$state_tmp"
chmod 600 "$state_tmp"
cp -p "$state_tmp" "$txn_dir/state.installed" || fail "Could not record the managed install state for rollback."
state_installed_digest="$("$PATH_OP" digest "$txn_dir/state.installed")" || exit 1
state_mutated=1
if [[ "$state_file_existed" == "1" ]]; then
  "$PATH_OP" publish "$state_tmp" "$STATE_FILE" --expected "$state_preimage_digest" || fail "install.env changed ownership before publication."
else
  "$PATH_OP" publish "$state_tmp" "$STATE_FILE" || fail "install.env appeared before publication."
fi
state_tmp=''

mkdir -p "$SYSTEMD_DIR"
unit_schema=current
unit_candidate="$(mktemp "${SYSTEMD_DIR}/hermesui-launcher-candidate-XXXXXX.service")" || fail "Could not create systemd unit candidate."
"$LAUNCHER_UNIT" write "$unit_candidate" \
  --repo-root "$REPO_ROOT" \
  --home "$HOME" \
  --hermes-home "$RESOLVED_HERMES_HOME" \
  --profile "$RESOLVED_PROFILE" \
  --host "$HOST" \
  --port "$PORT" || fail "Could not render the exact systemd launcher."
if ! "$SYSTEMD_ANALYZE" --user verify "$unit_candidate"; then
  rm -f "$unit_candidate"
  fail "Generated systemd unit failed validation."
fi
cp -p "$unit_candidate" "$txn_dir/unit.installed" || fail "Could not record the managed systemd unit for rollback."
unit_installed_digest="$("$PATH_OP" digest "$txn_dir/unit.installed")" || exit 1
unit_mutated=1
if [[ "$unit_file_existed" == "1" ]]; then
  "$PATH_OP" publish "$unit_candidate" "$UNIT_FILE" --expected "$unit_preimage_digest" || fail "The systemd unit changed ownership before publication."
else
  "$PATH_OP" publish "$unit_candidate" "$UNIT_FILE" || fail "The systemd unit appeared before publication."
fi
unit_candidate=''

published_unit_matches || fail "The systemd unit changed ownership before daemon reload."
"$SYSTEMCTL" --user daemon-reload
loaded_unit_matches || fail "The systemd unit changed ownership after daemon reload."
if [[ "$previous_enabled" != "1" ]]; then
  mkdir -p "$ENABLE_DIR"
  "$PATH_OP" symlink-create "$UNIT_FILE" "$ENABLE_LINK" \
    --expected-target-digest "$unit_installed_digest" || fail "The systemd unit or enable link changed ownership before publication."
  enable_link_created=1
fi
loaded_unit_matches || fail "The systemd launcher changed ownership before service start."
service_mutated=1
if [[ "$previous_active" == "1" ]]; then
  stop_owned_service "$RUNTIME_COMMIT:$RUNTIME_TREE" || fail "The prior managed HermesUI process could not be stopped safely."
fi
start_owned_service || fail "The HermesUI runtime could not be started atomically."
query_service_state || fail "The started HermesUI runtime state could not be queried."
[[ "$service_active_state" == "active" && "$service_load_state" == "loaded" && "$service_main_pid" -gt 1 ]] || fail "The started HermesUI runtime did not reach a stable active state."
verify_owned_service_pid "$service_main_pid" || fail "The started HermesUI process failed ownership verification."
loaded_unit_matches || fail "The systemd launcher changed ownership during service start."

local_health="http://${HOST}:${PORT}/health"
for _ in $(seq 1 90); do
  if "$CURL" -fsS --max-time 3 "$local_health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
"$CURL" -fsS --max-time 5 "$local_health" >/dev/null || fail "HermesUI did not become healthy at $local_health. Check: journalctl --user -u $SERVICE_NAME"
local_manifest="$($CURL -fsS --max-time 5 "http://${HOST}:${PORT}/manifest.json")"
python3 - "$local_manifest" <<'PY'
import json, sys
manifest = json.loads(sys.argv[1])
if manifest.get('name') != 'HermesUI':
    raise SystemExit('ERROR: local manifest does not identify HermesUI')
PY
ok "Local health and identity passed at $local_health"

installed_route_proxy="http://${HOST}:${PORT}"
route_mutated=1
serve_cas "${existing_route_proxy:-absent}" "$installed_route_proxy" >/dev/null
post_serve_status="$($TAILSCALE serve status --json 2>/dev/null)" || fail "Could not verify the final Tailscale Serve configuration."
if ! assert_no_funnel "$post_serve_status"; then
  fail "Unsafe final exposure state detected; rolling back the HermesUI Serve route."
fi
installed_route_proxy="$(assert_route_safe "$post_serve_status" required verified)" || exit 1
route_apply_confirmed=1

public_base="https://${dns_name}${BASE_PATH}/"

for _ in $(seq 1 30); do
  if "$CURL" -fsS --max-time 5 "${public_base}health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
"$CURL" -fsS --max-time 8 "${public_base}health" >/dev/null || fail "Tailnet health check failed at ${public_base}health."
manifest="$($CURL -fsS --max-time 8 "${public_base}manifest.json")"
python3 - "$manifest" <<'PY'
import json, sys
manifest = json.loads(sys.argv[1])
if manifest.get('name') != 'HermesUI':
    raise SystemExit('manifest name is not HermesUI')
for key in ('id', 'start_url', 'scope'):
    value = str(manifest.get(key, ''))
    if not value.startswith('./'):
        raise SystemExit(f'manifest {key} must be relative, got {value!r}')
print('OK: PWA manifest is HermesUI and subpath-relative')
PY

"$SYSTEMCTL" --user is-enabled "$LAUNCHER_NAME" >/dev/null
query_service_state || fail "$SERVICE_NAME final lifecycle state could not be queried."
[[ "$service_active_state" == "active" && "$service_load_state" == "loaded" && "$service_main_pid" -gt 1 ]] || fail "$SERVICE_NAME is not authoritatively active after setup."
verify_owned_service_pid "$service_main_pid" || fail "$SERVICE_NAME process ownership changed before final verification."
ok "$LAUNCHER_NAME is enabled and $SERVICE_NAME is active"

install_complete=1
printf '\nHermesUI is ready.\nURL: %s\nService: %s\nUninstall: %s/tailnet-uninstall.sh\n' "$public_base" "$SERVICE_NAME" "$INSTALLER_DIR"
