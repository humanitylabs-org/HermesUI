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

api_token_file=''
while (($#)); do
  case "$1" in
    --api-token-file) api_token_file="${2:-}"; shift 2 ;;
    *) printf 'ERROR: unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done
[[ -n "$api_token_file" ]] || { printf 'ERROR: --api-token-file is required so managed Cloudflare resources can be removed before local state.\n' >&2; exit 2; }
repo_root="${HERMESUI_REPO_ROOT_OVERRIDE:-$(cd "$installer_dir/../.." && pwd)}"
state_dir="${HERMESUI_STATE_DIR:-${XDG_CONFIG_HOME:-${HOME}/.config}/hermesui}"
state_file="${HERMESUI_STATE_FILE:-${state_dir}/install.env}"
cloudflare_state="${HERMESUI_CLOUDFLARE_STATE_FILE:-${state_dir}/cloudflare.json}"
connector_token="${HERMESUI_CONNECTOR_TOKEN_FILE:-${state_dir}/cloudflared.token}"
systemd_dir="${HERMESUI_SYSTEMD_DIR:-${HOME}/.config/systemd/user}"
app_unit="${systemd_dir}/hermesui.service"
tunnel_unit="${systemd_dir}/hermesui-cloudflared.service"
systemctl_bin="${HERMESUI_SYSTEMCTL:-systemctl}"
python_bin="${HERMESUI_PYTHON:-$(command -v python3)}"
cloudflared_bin="${HERMESUI_CLOUDFLARED:-$(command -v cloudflared)}"
provisioner="${HERMESUI_CLOUDFLARE_PROVISIONER:-${installer_dir}/cloudflare_provision.py}"
units_helper="${HERMESUI_CLOUDFLARE_UNITS_HELPER:-${installer_dir}/cloudflare_systemd_units.py}"
if [[ -r "$cloudflare_state" && ! -e "$state_file" ]]; then
  recovery_status="$("$python_bin" - "$cloudflare_state" <<'PY'
import json
import sys
from pathlib import Path

try:
    state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    print("")
else:
    print(state.get("status", ""))
PY
)"
  if [[ -e "$app_unit" || -L "$app_unit" || -e "$tunnel_unit" || -L "$tunnel_unit" ]]; then
    printf 'ERROR: local service units still exist but install.env is missing; refusing provider cleanup without an ownership proof.\n' >&2
    exit 1
  fi
  if [[ "$recovery_status" == "recovery_required" ]]; then
    "$python_bin" "$provisioner" cleanup \
      --api-token-file "$api_token_file" \
      --connector-token-file "$connector_token" \
      --state-file "$cloudflare_state"
    printf 'Incomplete Cloudflare provisioning was reconciled and cleaned. Hermes data was preserved.\n'
    exit 0
  elif [[ "$recovery_status" == "provider_resources_removed" ]]; then
    "$python_bin" - "$connector_token" "$cloudflare_state" <<'PY'
import os
import stat
import sys

for raw in sys.argv[1:]:
    path = os.path.abspath(raw)
    try:
        info = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        continue
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise SystemExit(f"ERROR: refusing to remove ambiguous local state path: {path}")
    os.unlink(path)
PY
    "$systemctl_bin" --user daemon-reload
    printf 'Wizard App Cloudflare uninstall finalization completed. Hermes data was preserved.\n'
    exit 0
  fi
fi
[[ -r "$state_file" && -r "$cloudflare_state" && -r "$connector_token" ]] || { printf 'ERROR: Cloudflare install state is incomplete.\n' >&2; exit 1; }
readarray -t local_state < <("$python_bin" - "$state_file" <<'PY'
import os
import stat
import sys

path = sys.argv[1]
info = os.stat(path, follow_symlinks=False)
if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
    raise SystemExit("ERROR: install state is not a regular owned file.")
values = {}
with open(path, encoding="utf-8") as handle:
    for raw in handle:
        key, separator, value = raw.rstrip("\n").partition("=")
        if not separator or key in values:
            raise SystemExit("ERROR: install state is malformed.")
        values[key] = value
required = {
    "HERMESUI_STATE_VERSION": "3",
    "HERMESUI_MODE": "standalone",
    "HERMESUI_ACCESS_MODE": "cloudflare",
    "HERMESUI_PROFILE": "default",
}
if any(values.get(key) != value for key, value in required.items()):
    raise SystemExit("ERROR: install state is not Cloudflare-owned.")
port = values.get("HERMESUI_PORT", "")
hermes_home = values.get("HERMESUI_HERMES_HOME", "")
if not port.isdigit() or not hermes_home:
    raise SystemExit("ERROR: install state is incomplete.")
print(port)
print(hermes_home)
PY
)
port="${local_state[0]}"
hermes_home="${local_state[1]}"
provider_status="$("$python_bin" - "$cloudflare_state" <<'PY'
import json
import sys
from pathlib import Path
print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")).get("status", "installed"))
PY
)"
if [[ "$provider_status" != "provider_resources_removed" ]]; then
  "$python_bin" "$units_helper" verify \
    --app-unit "$app_unit" --tunnel-unit "$tunnel_unit" \
    --repo-root "$repo_root" --home "$HOME" --hermes-home "$hermes_home" \
    --python "$python_bin" --cloudflared "$cloudflared_bin" --token-file "$connector_token" --port "$port"
  "$systemctl_bin" --user disable --now hermesui-cloudflared.service
  "$python_bin" "$provisioner" cleanup \
    --api-token-file "$api_token_file" \
    --connector-token-file "$connector_token" \
    --state-file "$cloudflare_state" \
    --preserve-connector-token \
    --preserve-state
fi
if [[ -e "$app_unit" || -L "$app_unit" ]]; then
  "$systemctl_bin" --user disable --now hermesui.service
fi
"$python_bin" "$units_helper" remove-existing \
  --app-unit "$app_unit" --tunnel-unit "$tunnel_unit" \
  --repo-root "$repo_root" --home "$HOME" --hermes-home "$hermes_home" \
  --python "$python_bin" --cloudflared "$cloudflared_bin" --token-file "$connector_token" --port "$port"
"$python_bin" - "$connector_token" "$state_file" "$cloudflare_state" <<'PY'
import os
import stat
import sys

for raw in sys.argv[1:]:
    path = os.path.abspath(raw)
    try:
        info = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        continue
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise SystemExit(f"ERROR: refusing to remove ambiguous local state path: {path}")
    os.unlink(path)
PY
"$systemctl_bin" --user daemon-reload
printf 'Wizard App and its installer-managed Cloudflare resources were removed. Hermes data was preserved.\n'
