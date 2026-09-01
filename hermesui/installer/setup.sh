#!/usr/bin/env bash
set -euo pipefail

mode=auto
forward=()
while (($#)); do
  case "$1" in
    --mode)
      [[ $# -ge 2 ]] || { printf 'ERROR: --mode needs a value.\n' >&2; exit 2; }
      mode="$2"; shift 2 ;;
    --mode=*) mode="${1#*=}"; shift ;;
    *) forward+=("$1"); shift ;;
  esac
done
[[ "$mode" == auto || "$mode" == cloudflare || "$mode" == tailscale ]] || { printf 'ERROR: mode must be auto, cloudflare, or tailscale.\n' >&2; exit 2; }
installer_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
state_file="${HERMESUI_STATE_FILE:-${XDG_CONFIG_HOME:-${HOME}/.config}/hermesui/install.env}"
cloudflare_setup="${HERMESUI_CLOUDFLARE_SETUP:-${installer_dir}/cloudflare-setup.sh}"
cloudflare_status="${HERMESUI_CLOUDFLARE_STATUS:-${installer_dir}/cloudflare-status.sh}"
tailnet_prereq="${HERMESUI_TAILNET_PREREQ:-${installer_dir}/tailnet-prereq-check.sh}"
tailnet_setup="${HERMESUI_TAILNET_SETUP:-${installer_dir}/tailnet-setup.sh}"

if [[ -r "$state_file" ]]; then
  access_mode="$(awk -F= '$1=="HERMESUI_ACCESS_MODE" {print $2}' "$state_file")"
  if [[ "$access_mode" == cloudflare ]]; then
    [[ "$mode" != tailscale ]] || { printf 'ERROR: this install is Cloudflare-owned; migration is not automatic.\n' >&2; exit 1; }
    exec "$cloudflare_status"
  fi
  [[ "$mode" != cloudflare ]] || { printf 'ERROR: an existing Tailscale install was found. Preserve it or uninstall it explicitly before migration.\n' >&2; exit 1; }
  exec "$tailnet_setup"
fi

case "$mode" in
  cloudflare) exec "$cloudflare_setup" "${forward[@]}" ;;
  tailscale) "$tailnet_prereq" && exec "$tailnet_setup" ;;
  auto)
    if printf '%s\n' "${forward[@]}" | grep -q -- '--hostname'; then
      exec "$cloudflare_setup" "${forward[@]}"
    fi
    printf 'ERROR: new installs prefer Cloudflare. Supply the Cloudflare hostname/account/zone/allowed-email/token-file arguments, or explicitly choose --mode tailscale.\n' >&2
    exit 1
    ;;
esac
