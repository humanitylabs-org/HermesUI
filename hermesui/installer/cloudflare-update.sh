#!/usr/bin/env bash
set -euo pipefail

INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${HERMESUI_REPO_ROOT_OVERRIDE:-$(cd "$INSTALLER_DIR/../.." && pwd)}"
TAG="${1:-}"
EXPECTED_COMMIT="${2:-}"
STATE_DIR="${HERMESUI_STATE_DIR:-${XDG_CONFIG_HOME:-${HOME}/.config}/hermesui}"
STATE_FILE="${HERMESUI_STATE_FILE:-${STATE_DIR}/install.env}"
CONNECTOR_TOKEN="${HERMESUI_CONNECTOR_TOKEN_FILE:-${STATE_DIR}/cloudflared.token}"
SYSTEMD_DIR="${HERMESUI_SYSTEMD_DIR:-${HOME}/.config/systemd/user}"
APP_UNIT_FILE="${SYSTEMD_DIR}/hermesui.service"
TUNNEL_UNIT_FILE="${SYSTEMD_DIR}/hermesui-cloudflared.service"
SYSTEMCTL="${HERMESUI_SYSTEMCTL:-systemctl}"
CURL="${HERMESUI_CURL:-curl}"
PYTHON="${HERMESUI_PYTHON:-$(command -v python3)}"
CLOUDFLARED="${HERMESUI_CLOUDFLARED:-$(command -v cloudflared || true)}"
LOCK_HELPER="${HERMESUI_LIFECYCLE_LOCK_HELPER:-${INSTALLER_DIR}/acquire-lifecycle-lock.py}"
LIFECYCLE_LOCK="${HERMESUI_LIFECYCLE_LOCK_FILE:-${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/hermesui-${UID}/lifecycle.lock}"

[[ "$TAG" =~ ^(exp-)?v[0-9]+\.[0-9]+\.[0-9]+$ && "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
  printf 'Usage: %s vX.Y.Z EXPECTED_40_HEX_COMMIT\n' "$0" >&2
  exit 2
}
[[ "$REPO_ROOT" == /* && -n "$PYTHON" && -n "$CLOUDFLARED" ]] || {
  printf 'ERROR: Cloudflare update prerequisites are incomplete.\n' >&2
  exit 1
}

if [[ "${HERMESUI_LIFECYCLE_LOCK_HELD:-0}" == "1" ]]; then
  "$PYTHON" "$LOCK_HELPER" --lock "$LIFECYCLE_LOCK" --fd 9 --verify-inherited || exit 75
else
  exec "$PYTHON" "$LOCK_HELPER" --lock "$LIFECYCLE_LOCK" --fd 9 -- "$INSTALLER_DIR/cloudflare-update.sh" "$@"
fi

cd "$REPO_ROOT"
[[ -z "$(git status --porcelain)" ]] || {
  printf 'ERROR: Refusing to replace a dirty Wizard App checkout. Preserve or remove its local changes first; Hermes data was not touched.\n' >&2
  exit 1
}

baseline_commit="$(git rev-parse --verify HEAD)"
baseline_tree="$(git rev-parse --verify 'HEAD^{tree}')"
[[ "$baseline_commit" =~ ^[0-9a-f]{40}$ && "$baseline_tree" =~ ^[0-9a-f]{40}$ ]] || {
  printf 'ERROR: Could not resolve the exact baseline commit/tree.\n' >&2
  exit 1
}
if baseline_branch="$(git symbolic-ref --quiet --short HEAD)"; then
  baseline_mode=branch
else
  baseline_mode=detached
  baseline_branch=''
fi

mapfile -t install_state < <("$PYTHON" - "$STATE_FILE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
try:
    raw = path.read_text(encoding="utf-8")
except OSError as exc:
    raise SystemExit(f"ERROR: Wizard App install state is unavailable: {exc}")
values = {}
for line in raw.splitlines():
    key, separator, value = line.partition("=")
    if separator != "=" or not key or key in values or "\x00" in value or "\n" in value:
        raise SystemExit("ERROR: Wizard App install state is malformed or ambiguous.")
    values[key] = value
required = {
    "HERMESUI_STATE_VERSION": "3",
    "HERMESUI_MODE": "standalone",
    "HERMESUI_ACCESS_MODE": "cloudflare",
    "HERMESUI_PROFILE": "default",
}
if any(values.get(key) != expected for key, expected in required.items()):
    raise SystemExit("ERROR: Existing installation is not a supported managed Cloudflare install.")
port = values.get("HERMESUI_PORT", "")
hermes_home = values.get("HERMESUI_HERMES_HOME", "")
if not port.isdigit() or not 1024 <= int(port) <= 65535 or not hermes_home.startswith("/"):
    raise SystemExit("ERROR: Existing Cloudflare install state is incomplete.")
print(port)
print(hermes_home)
PY
)
[[ "${#install_state[@]}" == 2 ]] || exit 1
PORT="${install_state[0]}"
HERMES_HOME="${install_state[1]}"

helper_dir="$(mktemp -d "${TMPDIR:-/tmp}/hermesui-cloudflare-update.XXXXXX")"
tag_ref="refs/hermesui-update/tag-$$"
STOP_HELPER_SOURCE="${HERMESUI_PROCESS_STOP:-${INSTALLER_DIR}/cloudflare-stop-owned-process.py}"
UNITS_HELPER_SOURCE="${HERMESUI_CLOUDFLARE_UNITS_HELPER:-${INSTALLER_DIR}/cloudflare_systemd_units.py}"
BASELINE_UNITS_HELPER_SOURCE="${HERMESUI_CLOUDFLARE_BASELINE_UNITS_HELPER:-${REPO_ROOT}/hermesui/installer/cloudflare_systemd_units.py}"
PATH_OP_SOURCE="${HERMESUI_PATH_OP:-${INSTALLER_DIR}/owned-path-op.py}"
cp "$STOP_HELPER_SOURCE" "$helper_dir/stop-owned-process.py"
cp "$UNITS_HELPER_SOURCE" "$helper_dir/candidate-cloudflare-systemd-units.py"
cp "$BASELINE_UNITS_HELPER_SOURCE" "$helper_dir/baseline-cloudflare-systemd-units.py"
cp "$PATH_OP_SOURCE" "$helper_dir/owned-path-op.py"
chmod 0600 "$helper_dir/"*.py

baseline_runtime=''
baseline_pid=''
baseline_tunnel_runtime=''
candidate_tree=''
checkout_changed=0
unit_changed=0
baseline_unit_digest=''
candidate_unit_digest=''
update_complete=0
rollback_in_progress=0

cleanup_tag_ref() {
  git update-ref -d "$tag_ref" >/dev/null 2>&1 || true
}

cleanup_refs() {
  cleanup_tag_ref
  rm -rf "$helper_dir"
}

preserve_recovery() {
  cleanup_tag_ref
  printf 'Recovery evidence was preserved at %s\n' "$helper_dir" >&2
}

restore_checkout() {
  if [[ "$baseline_mode" == branch ]]; then
    git checkout -q "$baseline_branch" || return 1
  else
    git checkout -q --detach "$baseline_commit" || return 1
  fi
  [[ "$(git rev-parse HEAD)" == "$baseline_commit" && "$(git rev-parse 'HEAD^{tree}')" == "$baseline_tree" ]]
}

units_operation() {
  local helper="$1" action="$2" app_unit="$3" tunnel_unit="$4"
  "$PYTHON" "$helper" "$action" \
    --app-unit "$app_unit" --tunnel-unit "$tunnel_unit" \
    --repo-root "$REPO_ROOT" --home "$HOME" --hermes-home "$HERMES_HOME" \
    --python "$PYTHON" --cloudflared "$CLOUDFLARED" --token-file "$CONNECTOR_TOKEN" --port "$PORT"
}

verify_baseline_units() {
  units_operation "$helper_dir/baseline-cloudflare-systemd-units.py" verify "$APP_UNIT_FILE" "$TUNNEL_UNIT_FILE"
}

verify_candidate_units() {
  units_operation "$helper_dir/candidate-cloudflare-systemd-units.py" verify "$APP_UNIT_FILE" "$TUNNEL_UNIT_FILE"
}

publish_candidate_unit() {
  local candidate_app candidate_tunnel tunnel_digest candidate_tunnel_digest
  candidate_app="${APP_UNIT_FILE}.candidate.$$"
  candidate_tunnel="${TUNNEL_UNIT_FILE}.candidate.$$"
  rm -f "$candidate_app" "$candidate_tunnel"
  units_operation "$helper_dir/candidate-cloudflare-systemd-units.py" write "$candidate_app" "$candidate_tunnel"

  tunnel_digest="$("$PYTHON" "$helper_dir/owned-path-op.py" digest "$TUNNEL_UNIT_FILE")"
  candidate_tunnel_digest="$("$PYTHON" "$helper_dir/owned-path-op.py" digest "$candidate_tunnel")"
  [[ "$candidate_tunnel_digest" == "$tunnel_digest" ]] || {
    rm -f "$candidate_app" "$candidate_tunnel"
    printf 'ERROR: Candidate unexpectedly changes the Cloudflare connector unit.\n' >&2
    return 1
  }
  rm -f "$candidate_tunnel"

  candidate_unit_digest="$("$PYTHON" "$helper_dir/owned-path-op.py" digest "$candidate_app")"
  "$PYTHON" "$helper_dir/owned-path-op.py" publish "$candidate_app" "$APP_UNIT_FILE" --expected "$baseline_unit_digest"
  unit_changed=1
  "$SYSTEMCTL" --user daemon-reload
}

restore_baseline_unit() {
  [[ "$unit_changed" == 1 ]] || return 0
  "$PYTHON" "$helper_dir/owned-path-op.py" publish \
    "$helper_dir/hermesui.service.preimage" "$APP_UNIT_FILE" --expected "$candidate_unit_digest" || return 1
  unit_changed=0
  "$SYSTEMCTL" --user daemon-reload || return 1
  verify_baseline_units
}

snapshot_baseline_unit() {
  baseline_unit_digest="$("$PYTHON" "$helper_dir/owned-path-op.py" digest "$APP_UNIT_FILE")"
  cp -p "$APP_UNIT_FILE" "$helper_dir/hermesui.service.preimage"
  [[ "$("$PYTHON" "$helper_dir/owned-path-op.py" digest "$helper_dir/hermesui.service.preimage")" == "$baseline_unit_digest" ]]
}

service_active() {
  "$SYSTEMCTL" --user is-active hermesui.service >/dev/null 2>&1
}

wait_inactive() {
  local state pid
  for _ in $(seq 1 150); do
    state="$($SYSTEMCTL --user show hermesui.service --property=ActiveState --value 2>/dev/null || true)"
    pid="$($SYSTEMCTL --user show hermesui.service --property=MainPID --value 2>/dev/null || true)"
    if [[ "$state" == inactive && "$pid" == 0 ]]; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

verify_owned_pid() {
  local pid="$1"
  "$PYTHON" "$helper_dir/stop-owned-process.py" \
    --verify-only --pid "$pid" --repo-root "$REPO_ROOT" --home "$HOME" \
    --hermes-home "$HERMES_HOME" --profile default --port "$PORT" \
    --systemd-unit hermesui.service --systemctl "$SYSTEMCTL"
}

stop_verified_service() {
  local pid
  pid="$($SYSTEMCTL --user show hermesui.service --property=MainPID --value)"
  [[ "$pid" =~ ^[0-9]+$ && "$pid" -gt 1 ]] || return 1
  verify_owned_pid "$pid" || return 1
  "$SYSTEMCTL" --user stop hermesui.service || return 1
  wait_inactive
}

health_idle() {
  "$PYTHON" - "$PORT" <<'PY'
import json
import sys
import urllib.request

with urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/health", timeout=5) as response:
    payload = json.load(response)
if payload.get("status") != "ok":
    raise SystemExit("Wizard App health is not ok")
if int(payload.get("active_runs") or 0) != 0 or int(payload.get("active_streams") or 0) != 0:
    raise SystemExit("Wizard App has active work; retry the update after it finishes")
PY
}

health_ok() {
  "$PYTHON" - "$PORT" <<'PY'
import json
import sys
import urllib.request

with urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/health", timeout=5) as response:
    payload = json.load(response)
if payload.get("status") != "ok":
    raise SystemExit("Wizard App health is not ok")
PY
}

rollback_update() {
  local status=$?
  [[ "$update_complete" == 1 ]] && { cleanup_refs; return "$status"; }
  [[ "$rollback_in_progress" == 0 ]] || return "$status"
  rollback_in_progress=1
  trap - EXIT
  set +e

  if service_active; then
    stop_verified_service >/dev/null 2>&1
    candidate_stop_status=$?
    if [[ "$candidate_stop_status" != 0 ]]; then
      printf 'ERROR: Candidate Wizard App could not be authoritatively stopped; checkout and recovery evidence were preserved. Hermes data was not changed.\n' >&2
      preserve_recovery
      exit "$status"
    fi
  fi

  unit_restore_status=0
  restore_baseline_unit >/dev/null 2>&1 || unit_restore_status=$?

  if ! restore_checkout; then
    printf 'ERROR: Update failed and the exact previous checkout could not be restored. Hermes data was not changed.\n' >&2
    preserve_recovery
    exit "$status"
  fi
  checkout_changed=0

  baseline_restore_status=0
  if [[ "$unit_restore_status" != 0 ]]; then
    baseline_restore_status=1
  fi
  if [[ "$baseline_runtime" == active ]]; then
    "$SYSTEMCTL" --user start hermesui.service >/dev/null 2>&1 || baseline_restore_status=$?
    if [[ "$baseline_restore_status" == 0 ]]; then
      for _ in $(seq 1 30); do health_ok >/dev/null 2>&1 && break; sleep 1; done
      health_ok >/dev/null 2>&1 || baseline_restore_status=$?
    fi
  elif [[ "$baseline_runtime" == inactive ]]; then
    if service_active; then baseline_restore_status=1; fi
  else
    baseline_restore_status=1
  fi

  if [[ "$baseline_restore_status" == 0 ]]; then
    printf 'ERROR: Update failed; restored the previous checkout and exact %s Wizard App runtime state. Hermes data was not changed.\n' "$baseline_runtime" >&2
  else
    printf 'ERROR: Update failed; previous checkout restoration is incomplete. Hermes data was not changed.\n' >&2
    preserve_recovery
    exit "$status"
  fi
  cleanup_refs
  exit "$status"
}
trap rollback_update EXIT

verify_baseline_units
snapshot_baseline_unit
"$SYSTEMCTL" --user is-enabled hermesui.service >/dev/null
"$SYSTEMCTL" --user is-enabled hermesui-cloudflared.service >/dev/null
if "$SYSTEMCTL" --user is-active hermesui-cloudflared.service >/dev/null 2>&1; then
  baseline_tunnel_runtime=active
else
  baseline_tunnel_runtime=inactive
fi
if service_active; then
  baseline_runtime=active
  baseline_pid="$($SYSTEMCTL --user show hermesui.service --property=MainPID --value)"
  verify_owned_pid "$baseline_pid"
  for _ in 1 2 3; do health_idle; sleep 1; done
else
  baseline_runtime=inactive
fi

remote_identity="$(git ls-remote origin "refs/tags/$TAG" "refs/tags/$TAG^{}")"
read -r remote_tag_oid remote_commit < <("$PYTHON" - "$remote_identity" "$TAG" <<'PY'
import re
import sys
raw, tag = sys.argv[1:]
oid = re.compile(r"^[0-9a-f]{40}$")
refs = {}
for line in raw.splitlines():
    value, separator, ref = line.partition("\t")
    if separator != "\t" or not oid.fullmatch(value) or ref in refs:
        raise SystemExit(1)
    refs[ref] = value
raw_ref = f"refs/tags/{tag}"
peeled_ref = f"{raw_ref}^{{}}"
if set(refs) != {raw_ref, peeled_ref}:
    raise SystemExit(1)
print(refs[raw_ref], refs[peeled_ref])
PY
) || {
  printf 'ERROR: Remote release tag is missing, lightweight, duplicate, or malformed.\n' >&2
  exit 1
}
[[ "$remote_commit" == "$EXPECTED_COMMIT" ]] || {
  printf 'ERROR: %s resolves to %s, not reviewed commit %s. Nothing was changed.\n' "$TAG" "$remote_commit" "$EXPECTED_COMMIT" >&2
  exit 1
}
git fetch --no-tags origin "refs/tags/$TAG:$tag_ref"
[[ "$(git cat-file -t "$tag_ref")" == tag ]]
[[ "$(git rev-parse "$tag_ref")" == "$remote_tag_oid" ]]
[[ "$(git rev-parse "$tag_ref^{commit}")" == "$EXPECTED_COMMIT" ]]
candidate_tree="$(git rev-parse "$EXPECTED_COMMIT^{tree}")"
[[ "$candidate_tree" =~ ^[0-9a-f]{40}$ ]]

if [[ "$baseline_runtime" == active ]]; then
  stop_verified_service || {
    printf 'ERROR: Could not safely stop the exact managed Wizard App runtime. Nothing was changed.\n' >&2
    exit 1
  }
fi

git checkout -q --detach "$EXPECTED_COMMIT"
checkout_changed=1
[[ "$(git rev-parse HEAD)" == "$EXPECTED_COMMIT" && "$(git rev-parse 'HEAD^{tree}')" == "$candidate_tree" ]]
publish_candidate_unit
verify_candidate_units

if [[ "$baseline_runtime" == active ]]; then
  "$SYSTEMCTL" --user start hermesui.service
  for _ in $(seq 1 30); do health_ok >/dev/null 2>&1 && break; sleep 1; done
  health_ok
  candidate_pid="$($SYSTEMCTL --user show hermesui.service --property=MainPID --value)"
  [[ "$candidate_pid" =~ ^[0-9]+$ && "$candidate_pid" -gt 1 && "$candidate_pid" != "$baseline_pid" ]]
  verify_owned_pid "$candidate_pid"
fi
[[ "$(git rev-parse HEAD)" == "$EXPECTED_COMMIT" && "$(git rev-parse 'HEAD^{tree}')" == "$candidate_tree" ]]
[[ -d "$HERMES_HOME" ]]
if [[ "$baseline_tunnel_runtime" == active ]]; then
  "$SYSTEMCTL" --user is-active hermesui-cloudflared.service >/dev/null
else
  ! "$SYSTEMCTL" --user is-active hermesui-cloudflared.service >/dev/null 2>&1
fi

update_complete=1
trap - EXIT
cleanup_refs
printf 'Wizard App updated to %s at reviewed commit %s (tree %s); Hermes home %s was preserved.\n' "$TAG" "$EXPECTED_COMMIT" "$candidate_tree" "$HERMES_HOME"
