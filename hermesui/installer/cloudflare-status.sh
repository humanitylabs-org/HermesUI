#!/usr/bin/env bash
set -euo pipefail
installer_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
units_helper="${HERMESUI_CLOUDFLARE_UNITS_HELPER:-${installer_dir}/cloudflare_systemd_units.py}"
[[ -r "$state_file" ]] || { printf 'ERROR: Wizard App install state is missing.\n' >&2; exit 1; }
declare -A state=()
while IFS='=' read -r key value; do
  [[ -z "${state[$key]+x}" ]] || { printf 'ERROR: duplicate install-state key.\n' >&2; exit 1; }
  state[$key]="$value"
done <"$state_file"
[[ "${state[HERMESUI_STATE_VERSION]:-}" == 3 && "${state[HERMESUI_ACCESS_MODE]:-}" == cloudflare && "${state[HERMESUI_MODE]:-}" == standalone && "${state[HERMESUI_PROFILE]:-}" == default ]] || { printf 'ERROR: install state is not a supported Cloudflare install.\n' >&2; exit 1; }
port="${state[HERMESUI_PORT]:-}"
hermes_home="${state[HERMESUI_HERMES_HOME]:-}"
hostname="${state[HERMESUI_HOSTNAME]:-}"
[[ "$port" =~ ^[0-9]+$ && -n "$hermes_home" && -n "$hostname" ]] || { printf 'ERROR: install state is incomplete.\n' >&2; exit 1; }
auth_domain="$("$python_bin" - "$cloudflare_state" <<'PY'
import json
import re
import sys

domain = str(json.load(open(sys.argv[1], encoding="utf-8")).get("auth_domain", "")).strip().lower()
if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", domain) or "." not in domain:
    raise SystemExit("ERROR: Cloudflare state has no valid Access authentication domain.")
print(domain)
PY
)"
"$python_bin" "$units_helper" verify \
  --app-unit "$app_unit" --tunnel-unit "$tunnel_unit" \
  --repo-root "$repo_root" --home "$HOME" --hermes-home "$hermes_home" \
  --python "$python_bin" --cloudflared "$cloudflared_bin" --token-file "$connector_token" --port "$port"
"$systemctl_bin" --user is-enabled hermesui.service >/dev/null
"$systemctl_bin" --user is-enabled hermesui-cloudflared.service >/dev/null
"$systemctl_bin" --user is-active hermesui.service >/dev/null
"$systemctl_bin" --user is-active hermesui-cloudflared.service >/dev/null
"$curl_bin" -fsS --max-time 5 "http://127.0.0.1:${port}/health" >/dev/null
headers="$($curl_bin -sS --max-time 8 --output /dev/null --dump-header - "https://${hostname}/" || true)"
if ! printf '%s' "$headers" | "$python_bin" -c "import re,sys; from urllib.parse import urlparse; expected=sys.argv[1]; s=sys.stdin.read(); blocks=[b for b in re.split(r'\\r?\\n\\r?\\n',s) if b.startswith('HTTP/')]; ok=False
if blocks:
 lines=blocks[-1].splitlines(); parts=lines[0].split(); status=int(parts[1]) if len(parts)>1 and parts[1].isdigit() else 0; loc=' '.join(x.split(':',1)[1].strip() for x in lines[1:] if x.lower().startswith('location:')); target=urlparse(loc); ok=status in {302,303} and target.scheme == 'https' and (target.hostname or '').lower() == expected and target.path.startswith('/cdn-cgi/access/')
sys.exit(0 if ok else 1)" "$auth_domain"; then
  printf 'ERROR: public status does not prove Cloudflare Access for the configured hostname.\n' >&2
  exit 1
fi
printf 'Mode: standalone\nAccess: Cloudflare Tunnel + Access\nOrigin: http://127.0.0.1:%s\nWizard App URL: https://%s/\n' "$port" "$hostname"
