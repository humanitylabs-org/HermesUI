#!/usr/bin/env bash
set -euo pipefail

original_args=("$@")
installer_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
lock_helper="${HERMESUI_LIFECYCLE_LOCK_HELPER:-${installer_dir}/acquire-lifecycle-lock.py}"
lifecycle_lock="${HERMESUI_LIFECYCLE_LOCK_FILE:-${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/hermesui-${UID}/lifecycle.lock}"
if [[ "${HERMESUI_LIFECYCLE_LOCK_HELD:-0}" == 1 ]]; then
  python3 "$lock_helper" --lock "$lifecycle_lock" --fd 9 --verify-inherited || exit 75
else
  exec python3 "$lock_helper" --lock "$lifecycle_lock" --fd 9 -- "$0" "${original_args[@]}"
fi

PORT="${HERMESUI_PORT:-8793}"
account_id=''
zone_id=''
hostname=''
api_token_file=''
allowed_emails=()
usage() {
  printf 'Usage: %s --account-id ID --zone-id ID --hostname HOST --allow-email EMAIL [--allow-email EMAIL...] --api-token-file PATH\n' "$0"
}
while (($#)); do
  case "$1" in
    --account-id) account_id="${2:-}"; shift 2 ;;
    --zone-id) zone_id="${2:-}"; shift 2 ;;
    --hostname) hostname="${2:-}"; shift 2 ;;
    --allow-email) allowed_emails+=("${2:-}"); shift 2 ;;
    --api-token-file) api_token_file="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'ERROR: unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ -n "$account_id" && -n "$zone_id" && -n "$hostname" && -n "$api_token_file" && ${#allowed_emails[@]} -gt 0 ]] || { usage >&2; exit 2; }
if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1024 || PORT > 65535 )); then
  printf 'ERROR: invalid HERMESUI_PORT.\n' >&2
  exit 2
fi

repo_root="${HERMESUI_REPO_ROOT_OVERRIDE:-$(cd "$installer_dir/../.." && pwd)}"
state_dir="${HERMESUI_STATE_DIR:-${XDG_CONFIG_HOME:-${HOME}/.config}/hermesui}"
state_file="${HERMESUI_STATE_FILE:-${state_dir}/install.env}"
cloudflare_state="${HERMESUI_CLOUDFLARE_STATE_FILE:-${state_dir}/cloudflare.json}"
connector_token="${HERMESUI_CONNECTOR_TOKEN_FILE:-${state_dir}/cloudflared.token}"
systemd_dir="${HERMESUI_SYSTEMD_DIR:-${HOME}/.config/systemd/user}"
app_unit="${systemd_dir}/hermesui.service"
tunnel_unit="${systemd_dir}/hermesui-cloudflared.service"
systemctl_bin="${HERMESUI_SYSTEMCTL:-systemctl}"
curl_bin="${HERMESUI_CURL:-curl}"
python_bin="${HERMESUI_PYTHON:-$(command -v python3)}"
cloudflared_bin="${HERMESUI_CLOUDFLARED:-$(command -v cloudflared)}"
provisioner="${HERMESUI_CLOUDFLARE_PROVISIONER:-${installer_dir}/cloudflare_provision.py}"
units_helper="${HERMESUI_CLOUDFLARE_UNITS_HELPER:-${installer_dir}/cloudflare_systemd_units.py}"
prereq="${HERMESUI_CLOUDFLARE_PREREQ:-${installer_dir}/cloudflare-prereq-check.sh}"
hermes_home="${HERMES_HOME:-${HOME}/.hermes}"
origin="http://127.0.0.1:${PORT}"
tunnel_name="HermesUI ${hostname,,}"

"$prereq"
[[ -d "$repo_root/.git" || -f "$repo_root/.git" ]] || { printf 'ERROR: repository checkout is not a Git worktree.\n' >&2; exit 1; }
[[ -z "$(git -C "$repo_root" status --porcelain --untracked-files=no)" ]] || { printf 'ERROR: repository checkout has tracked local changes.\n' >&2; exit 1; }
[[ -d "$hermes_home" ]] || { printf 'ERROR: Hermes home does not exist: %s\n' "$hermes_home" >&2; exit 1; }
for path in "$state_file" "$cloudflare_state" "$connector_token" "$app_unit" "$tunnel_unit"; do
  [[ ! -e "$path" && ! -L "$path" ]] || { printf 'ERROR: refusing to overwrite existing install path: %s\n' "$path" >&2; exit 1; }
done
for unit in hermesui.service hermesui-cloudflared.service hermesui-launcher.service; do
  if "$systemctl_bin" --user cat "$unit" >/dev/null 2>&1; then
    printf 'ERROR: systemd unit already exists: %s\n' "$unit" >&2
    exit 1
  fi
done

mkdir -p "$state_dir" "$systemd_dir"
chmod 700 "$state_dir"
provisioned=0
units_written=0
app_start_attempted=0
tunnel_start_attempted=0
cleanup_failed_install() {
  status=$?
  trap - EXIT
  local_cleanup_ok=1
  if [[ "$units_written" == 1 ]]; then
    if "$python_bin" "$units_helper" verify \
      --app-unit "$app_unit" --tunnel-unit "$tunnel_unit" \
      --repo-root "$repo_root" --home "$HOME" --hermes-home "$hermes_home" \
      --python "$python_bin" --cloudflared "$cloudflared_bin" --token-file "$connector_token" --port "$PORT"; then
      if [[ "$tunnel_start_attempted" == 1 ]]; then
        "$systemctl_bin" --user disable --now hermesui-cloudflared.service >/dev/null 2>&1 || true
      fi
      if [[ "$app_start_attempted" == 1 ]]; then
        "$systemctl_bin" --user disable --now hermesui.service >/dev/null 2>&1 || true
      fi
      if ! "$python_bin" "$units_helper" remove \
        --app-unit "$app_unit" --tunnel-unit "$tunnel_unit" \
        --repo-root "$repo_root" --home "$HOME" --hermes-home "$hermes_home" \
        --python "$python_bin" --cloudflared "$cloudflared_bin" --token-file "$connector_token" --port "$PORT"; then
        printf 'ERROR: managed systemd units changed during rollback and were preserved.\n' >&2
        local_cleanup_ok=0
      fi
      "$systemctl_bin" --user daemon-reload >/dev/null 2>&1 || true
    else
      printf 'ERROR: managed systemd units changed during rollback and were preserved.\n' >&2
      local_cleanup_ok=0
    fi
  fi
  if [[ "$provisioned" == 1 && -r "$cloudflare_state" && "$local_cleanup_ok" == 1 ]]; then
    "$python_bin" "$provisioner" cleanup \
      --api-token-file "$api_token_file" \
      --connector-token-file "$connector_token" \
      --state-file "$cloudflare_state" || printf 'ERROR: Cloudflare rollback was incomplete; connector remains stopped.\n' >&2
  fi
  exit "$status"
}
trap cleanup_failed_install EXIT

provision_args=(
  apply
  --account-id "$account_id"
  --zone-id "$zone_id"
  --hostname "$hostname"
  --origin-url "$origin"
  --tunnel-name "$tunnel_name"
  --api-token-file "$api_token_file"
  --connector-token-file "$connector_token"
  --state-file "$cloudflare_state"
)
for email in "${allowed_emails[@]}"; do provision_args+=(--allow-email "$email"); done
if ! "$python_bin" "$provisioner" "${provision_args[@]}"; then
  if [[ -r "$cloudflare_state" ]]; then
    printf 'ERROR: Cloudflare returned an ambiguous or incomplete mutation. Do not retry setup blindly. Run %q --api-token-file %q after provider connectivity is restored.\n' "${installer_dir}/cloudflare-uninstall.sh" "$api_token_file" >&2
  fi
  exit 1
fi
provisioned=1

"$python_bin" "$units_helper" write \
  --app-unit "$app_unit" --tunnel-unit "$tunnel_unit" \
  --repo-root "$repo_root" --home "$HOME" --hermes-home "$hermes_home" \
  --python "$python_bin" --cloudflared "$cloudflared_bin" --token-file "$connector_token" --port "$PORT"
units_written=1
systemd-analyze --user verify "$app_unit" "$tunnel_unit"
"$systemctl_bin" --user daemon-reload
app_start_attempted=1
"$systemctl_bin" --user enable --now hermesui.service
for _ in $(seq 1 30); do
  "$curl_bin" -fsS --max-time 3 "$origin/health" >/dev/null 2>&1 && break
  sleep 1
done
"$curl_bin" -fsS --max-time 5 "$origin/health" >/dev/null
tunnel_start_attempted=1
"$systemctl_bin" --user enable --now hermesui-cloudflared.service
"$systemctl_bin" --user is-active hermesui.service >/dev/null
"$systemctl_bin" --user is-active hermesui-cloudflared.service >/dev/null

access_domain="$("$python_bin" - "$cloudflare_state" <<'PY'
import json, re, sys
state = json.load(open(sys.argv[1], encoding='utf-8'))
domain = str(state.get('auth_domain', '')).strip().lower()
if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', domain) or '.' not in domain:
    raise SystemExit('ERROR: Cloudflare state has no valid Access authentication domain.')
print(domain)
PY
)"
access_gate_attempts="${HERMESUI_ACCESS_GATE_ATTEMPTS:-30}"
access_gate_delay="${HERMESUI_ACCESS_GATE_DELAY:-1}"
if [[ ! "$access_gate_attempts" =~ ^[0-9]+$ ]] || (( access_gate_attempts < 1 || access_gate_attempts > 60 )); then
  printf 'ERROR: invalid Access gate attempt count.\n' >&2
  exit 1
fi
if [[ ! "$access_gate_delay" =~ ^[0-9]+$ ]] || (( access_gate_delay > 10 )); then
  printf 'ERROR: invalid Access gate retry delay.\n' >&2
  exit 1
fi
headers="$(mktemp)"
trap 'rm -f "$headers"' RETURN
access_ok=0
for _ in $(seq 1 "$access_gate_attempts"); do
  : >"$headers"
  "$curl_bin" -sS --max-time 8 --output /dev/null --dump-header "$headers" "https://${hostname,,}/" >/dev/null 2>&1 || true
  if "$python_bin" - "$headers" "$access_domain" <<'PY'
import re, sys
from urllib.parse import urlparse
text = open(sys.argv[1], encoding='iso-8859-1').read()
expected_domain = sys.argv[2]
blocks = [block for block in re.split(r'\r?\n\r?\n', text) if block.startswith('HTTP/')]
if not blocks:
    raise SystemExit(1)
lines = blocks[-1].splitlines()
status = int(lines[0].split()[1])
headers = {}
for line in lines[1:]:
    if ':' in line:
        key, value = line.split(':', 1)
        headers.setdefault(key.strip().lower(), []).append(value.strip())
location = ' '.join(headers.get('location', []))
if status not in {302, 303}:
    raise SystemExit(1)
target = urlparse(location)
if target.scheme != 'https' or (target.hostname or '').lower() != expected_domain:
    raise SystemExit(1)
if not target.path.startswith('/cdn-cgi/access/'):
    raise SystemExit(1)
PY
  then access_ok=1; break; fi
  sleep "$access_gate_delay"
done
rm -f "$headers"
[[ "$access_ok" == 1 ]] || { printf 'ERROR: public hostname did not prove a Cloudflare Access gate.\n' >&2; exit 1; }

"$python_bin" - "$state_file" "$PORT" "$hermes_home" "${hostname,,}" <<'PY'
import os
import sys

path, port, hermes_home, hostname = sys.argv[1:]
payload = (
    "HERMESUI_STATE_VERSION=3\n"
    "HERMESUI_MODE=standalone\n"
    "HERMESUI_ACCESS_MODE=cloudflare\n"
    f"HERMESUI_PORT={port}\n"
    f"HERMESUI_HERMES_HOME={hermes_home}\n"
    "HERMESUI_PROFILE=default\n"
    f"HERMESUI_HOSTNAME={hostname}\n"
).encode()
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
fd = os.open(path, flags, 0o600)
try:
    written = 0
    while written < len(payload):
        written += os.write(fd, payload[written:])
    os.fsync(fd)
finally:
    os.close(fd)
PY

trap - EXIT
printf '\nWizard App is ready at https://%s/\n' "${hostname,,}"
printf 'Origin: %s (loopback only)\nAccess mode: Cloudflare Tunnel + Access\n' "$origin"
