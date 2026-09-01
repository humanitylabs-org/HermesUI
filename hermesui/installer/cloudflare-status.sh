#!/usr/bin/env bash
set -euo pipefail
installer_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="${HERMESUI_REPO_ROOT_OVERRIDE:-$(cd "$installer_dir/../.." && pwd)}"
state_dir="${HERMESUI_STATE_DIR:-${XDG_CONFIG_HOME:-${HOME}/.config}/hermesui}"
state_file="${HERMESUI_STATE_FILE:-${state_dir}/install.env}"
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
printf '%s' "$headers" | "$python_bin" -c "import re,sys; s=sys.stdin.read(); blocks=[b for b in re.split(r'\\r?\\n\\r?\\n',s) if b.startswith('HTTP/')]; assert blocks; lines=blocks[-1].splitlines(); status=int(lines[0].split()[1]); loc=' '.join(x.split(':',1)[1].strip() for x in lines[1:] if x.lower().startswith('location:')); assert status in {302,303,401,403}; assert status not in {302,303} or 'cloudflareaccess.com' in loc or '/cdn-cgi/access/' in loc"
printf 'Mode: standalone\nAccess: Cloudflare Tunnel + Access\nOrigin: http://127.0.0.1:%s\nWizard App URL: https://%s/\n' "$port" "$hostname"
