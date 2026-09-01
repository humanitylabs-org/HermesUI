#!/usr/bin/env bash
set -euo pipefail
api_token_file=''
while (($#)); do
  case "$1" in
    --api-token-file) api_token_file="${2:-}"; shift 2 ;;
    *) printf 'ERROR: unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done
[[ -n "$api_token_file" ]] || { printf 'ERROR: --api-token-file is required so managed Cloudflare resources can be removed before local state.\n' >&2; exit 2; }
installer_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
state_dir="${HERMESUI_STATE_DIR:-${XDG_CONFIG_HOME:-${HOME}/.config}/hermesui}"
state_file="${HERMESUI_STATE_FILE:-${state_dir}/install.env}"
cloudflare_state="${HERMESUI_CLOUDFLARE_STATE_FILE:-${state_dir}/cloudflare.json}"
connector_token="${HERMESUI_CONNECTOR_TOKEN_FILE:-${state_dir}/cloudflared.token}"
mkdir -p "$state_dir"
chmod 700 "$state_dir"
exec 9>"$state_dir/setup.lock"
flock -n 9 || { printf 'ERROR: another Wizard App setup or uninstall is already running.\n' >&2; exit 1; }
systemd_dir="${HERMESUI_SYSTEMD_DIR:-${HOME}/.config/systemd/user}"
app_unit="${systemd_dir}/hermesui.service"
tunnel_unit="${systemd_dir}/hermesui-cloudflared.service"
systemctl_bin="${HERMESUI_SYSTEMCTL:-systemctl}"
python_bin="${HERMESUI_PYTHON:-$(command -v python3)}"
provisioner="${HERMESUI_CLOUDFLARE_PROVISIONER:-${installer_dir}/cloudflare_provision.py}"
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
  if [[ "$recovery_status" == "recovery_required" ]]; then
    "$python_bin" "$provisioner" cleanup \
      --api-token-file "$api_token_file" \
      --connector-token-file "$connector_token" \
      --state-file "$cloudflare_state"
    printf 'Incomplete Cloudflare provisioning was reconciled and cleaned. Hermes data was preserved.\n'
    exit 0
  fi
fi
[[ -r "$state_file" && -r "$cloudflare_state" && -r "$connector_token" ]] || { printf 'ERROR: Cloudflare install state is incomplete.\n' >&2; exit 1; }
grep -qx 'HERMESUI_ACCESS_MODE=cloudflare' "$state_file" || { printf 'ERROR: install state is not Cloudflare-owned.\n' >&2; exit 1; }
grep -qx '# Managed by HermesUI Cloudflare installer: application' <(head -n 1 "$app_unit") || { printf 'ERROR: HermesUI unit ownership is ambiguous.\n' >&2; exit 1; }
grep -qx '# Managed by HermesUI Cloudflare installer: connector' <(head -n 1 "$tunnel_unit") || { printf 'ERROR: connector unit ownership is ambiguous.\n' >&2; exit 1; }
"$systemctl_bin" --user disable --now hermesui-cloudflared.service
"$python_bin" "$provisioner" cleanup \
  --api-token-file "$api_token_file" \
  --connector-token-file "$connector_token" \
  --state-file "$cloudflare_state"
"$systemctl_bin" --user disable --now hermesui.service
rm -f "$app_unit" "$tunnel_unit" "$state_file"
"$systemctl_bin" --user daemon-reload
printf 'Wizard App and its installer-managed Cloudflare resources were removed. Hermes data was preserved.\n'
