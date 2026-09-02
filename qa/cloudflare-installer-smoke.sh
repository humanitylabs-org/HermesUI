#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT
HOME_DIR="$TMP/home"
REPO="$TMP/HermesUI"
BIN="$TMP/bin"
STATE="$HOME_DIR/.config/hermesui"
SYSTEMD="$HOME_DIR/.config/systemd/user"
LOG="$TMP/actions.log"
mkdir -p "$HOME_DIR/.hermes" "$REPO/hermesui/installer" "$BIN" "$STATE" "$SYSTEMD"
cp "$ROOT/bootstrap.py" "$REPO/bootstrap.py"
cp "$ROOT/hermesui/installer/runtime-home-guard.py" "$REPO/hermesui/installer/runtime-home-guard.py"
git init -q -b main "$REPO"
git -C "$REPO" config user.name 'Cloudflare Installer QA'
git -C "$REPO" config user.email 'qa@example.invalid'
git -C "$REPO" add .
git -C "$REPO" commit -q -m fixture

cat >"$BIN/cloudflared" <<'SH'
#!/usr/bin/env bash
exit 0
SH
cat >"$BIN/prereq" <<'SH'
#!/usr/bin/env bash
exit 0
SH
cat >"$BIN/systemctl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf 'systemctl %s\n' "$*" >>"$HERMESUI_QA_LOG"
args=("$@")
if [[ " ${args[*]} " == *' cat '* ]]; then exit 1; fi
if [[ -n "${HERMESUI_QA_FAIL_APP_DISABLE_ONCE:-}" && " ${args[*]} " == *' disable --now hermesui.service '* && ! -e "$HERMESUI_QA_FAIL_APP_DISABLE_ONCE" ]]; then
  : >"$HERMESUI_QA_FAIL_APP_DISABLE_ONCE"
  exit 42
fi
exit 0
SH
cat >"$BIN/curl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
dump=''
url=''
while (($#)); do
  case "$1" in
    --dump-header) dump="${2:-}"; shift 2 ;;
    http://*|https://*) url="$1"; shift ;;
    *) shift ;;
  esac
done
if [[ "$url" == http://127.0.0.1:* ]]; then
  printf '{"status":"ok"}\n'
  exit 0
fi
if [[ "${HERMESUI_QA_GATE_MODE:-access}" == generic403 ]]; then
  headers=$'HTTP/2 403\r\ncontent-type: text/plain\r\n\r\n'
else
  headers=$'HTTP/2 302\r\nlocation: https://team.cloudflareaccess.com/cdn-cgi/access/login/wizard.example.com\r\n\r\n'
fi
if [[ -n "$dump" ]]; then
  if [[ "$dump" == - ]]; then printf '%s' "$headers"; else printf '%s' "$headers" >"$dump"; fi
fi
exit 0
SH
cat >"$BIN/provisioner" <<'PY'
#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

action, *args = sys.argv[1:]
values = {}
emails = []
index = 0
while index < len(args):
    key = args[index]
    if key in {'--preserve-connector-token', '--preserve-state'}:
        values[key] = True
        index += 1
        continue
    value = args[index + 1]
    index += 2
    if key == '--allow-email':
        emails.append(value)
    else:
        values[key] = value
with open(os.environ['HERMESUI_QA_LOG'], 'a', encoding='utf-8') as handle:
    handle.write(f'provision {action}\n')
connector = Path(values['--connector-token-file'])
state = Path(values['--state-file'])
if action == 'apply':
    connector.parent.mkdir(parents=True, exist_ok=True)
    connector.write_text('fake-connector-token\n', encoding='utf-8')
    connector.chmod(0o600)
    payload = {
        'version': 1,
        'account_id': values['--account-id'],
        'zone_id': values['--zone-id'],
        'hostname': values['--hostname'],
        'origin_url': values['--origin-url'],
        'allowed_emails': emails,
        'auth_domain': 'team.cloudflareaccess.com',
        'tunnel_name': values['--tunnel-name'],
        'managed': {'access_app': True, 'dns_record': True, 'tunnel': True},
    }
    state.write_text(json.dumps(payload), encoding='utf-8')
    state.chmod(0o600)
else:
    if not values.get('--preserve-connector-token'):
        connector.unlink(missing_ok=True)
    if values.get('--preserve-state'):
        payload = json.loads(state.read_text(encoding='utf-8'))
        payload['status'] = 'provider_resources_removed'
        state.write_text(json.dumps(payload), encoding='utf-8')
        state.chmod(0o600)
    else:
        state.unlink(missing_ok=True)
PY
cat >"$BIN/tailnet-prereq" <<'SH'
#!/usr/bin/env bash
printf 'tailnet-prereq\n' >>"$HERMESUI_QA_LOG"
SH
cat >"$BIN/tailnet-setup" <<'SH'
#!/usr/bin/env bash
printf 'tailnet-setup\n' >>"$HERMESUI_QA_LOG"
SH
chmod +x "$BIN"/*
printf 'fake-api-token\n' >"$STATE/api-token"; chmod 600 "$STATE/api-token"

export HOME="$HOME_DIR"
export PATH="$BIN:/usr/bin:/bin"
export HERMES_HOME="$HOME_DIR/.hermes"
export HERMESUI_QA_LOG="$LOG"
export HERMESUI_REPO_ROOT_OVERRIDE="$REPO"
export HERMESUI_STATE_DIR="$STATE"
export HERMESUI_STATE_FILE="$STATE/install.env"
export HERMESUI_CLOUDFLARE_STATE_FILE="$STATE/cloudflare.json"
export HERMESUI_CONNECTOR_TOKEN_FILE="$STATE/cloudflared.token"
export HERMESUI_SYSTEMD_DIR="$SYSTEMD"
export HERMESUI_SYSTEMCTL="$BIN/systemctl"
export HERMESUI_CURL="$BIN/curl"
qa_python="$(command -v python3)"
export HERMESUI_PYTHON="$qa_python"
export HERMESUI_CLOUDFLARED="$BIN/cloudflared"
export HERMESUI_CLOUDFLARE_PROVISIONER="$BIN/provisioner"
export HERMESUI_CLOUDFLARE_UNITS_HELPER="$ROOT/hermesui/installer/cloudflare_systemd_units.py"
export HERMESUI_CLOUDFLARE_PREREQ="$BIN/prereq"
export HERMESUI_CLOUDFLARE_SETUP="$ROOT/hermesui/installer/cloudflare-setup.sh"
export HERMESUI_CLOUDFLARE_STATUS="$ROOT/hermesui/installer/cloudflare-status.sh"
export HERMESUI_TAILNET_PREREQ="$BIN/tailnet-prereq"
export HERMESUI_TAILNET_SETUP="$BIN/tailnet-setup"
export HERMESUI_ACCESS_GATE_ATTEMPTS=1
export HERMESUI_ACCESS_GATE_DELAY=0
export HERMESUI_LIFECYCLE_LOCK_FILE="$TMP/runtime/hermesui/lifecycle.lock"

mkdir -p "$TMP/runtime/hermesui"
chmod 700 "$TMP/runtime/hermesui"
# shellcheck disable=SC2016
"$qa_python" "$ROOT/hermesui/installer/acquire-lifecycle-lock.py" \
  --lock "$HERMESUI_LIFECYCLE_LOCK_FILE" --fd 9 -- \
  bash -c 'printf ready >"$1"; sleep 30' _ "$TMP/lock-ready" &
lock_pid=$!
for _ in $(seq 1 50); do [[ -e "$TMP/lock-ready" ]] && break; sleep 0.1; done
[[ -e "$TMP/lock-ready" ]] || { printf 'Lifecycle lock fixture did not start.\n' >&2; exit 1; }
if "$ROOT/hermesui/installer/setup.sh" --mode cloudflare \
  --account-id account --zone-id zone --hostname wizard.example.com \
  --allow-email owner@example.com --api-token-file "$STATE/api-token" \
  >"$TMP/locked.out" 2>"$TMP/locked.err"; then
  printf 'Concurrent Cloudflare setup unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q 'another HermesUI setup, update, or uninstall is already running' "$TMP/locked.err"
kill "$lock_pid"
wait "$lock_pid" 2>/dev/null || true

printf '%s\n' '{"status":"recovery_required"}' >"$STATE/cloudflare.json"
chmod 600 "$STATE/cloudflare.json"
"$ROOT/hermesui/installer/cloudflare-uninstall.sh" --api-token-file "$STATE/api-token"
[[ ! -e "$STATE/cloudflare.json" ]] || { printf 'ERROR: recovery state was not cleaned.\n' >&2; exit 1; }

export HERMESUI_QA_GATE_MODE=generic403
if "$ROOT/hermesui/installer/setup.sh" --mode cloudflare \
  --account-id account --zone-id zone --hostname wizard.example.com \
  --allow-email owner@example.com --api-token-file "$STATE/api-token" \
  >"$TMP/generic403.out" 2>"$TMP/generic403.err"; then
  printf 'A generic provider 403 was incorrectly accepted as proof of Cloudflare Access.\n' >&2
  exit 1
fi
grep -q 'did not prove a Cloudflare Access gate' "$TMP/generic403.err"
[[ ! -e "$STATE/install.env" && ! -e "$STATE/cloudflare.json" && ! -e "$STATE/cloudflared.token" ]]
[[ ! -e "$SYSTEMD/hermesui.service" && ! -e "$SYSTEMD/hermesui-cloudflared.service" ]]
unset HERMESUI_QA_GATE_MODE

disable_count_before="$(grep -c 'systemctl --user disable' "$LOG" || true)"
ln -s "$TMP/foreign-missing-install-state" "$STATE/install.env"
if "$ROOT/hermesui/installer/setup.sh" --mode cloudflare \
  --account-id account --zone-id zone --hostname wizard.example.com \
  --allow-email owner@example.com --api-token-file "$STATE/api-token" \
  >"$TMP/dangling.out" 2>"$TMP/dangling.err"; then
  printf 'Setup unexpectedly overwrote a dangling install-state symlink.\n' >&2
  exit 1
fi
grep -q 'refusing to overwrite existing install path' "$TMP/dangling.err"
[[ -L "$STATE/install.env" ]]
[[ "$disable_count_before" == "$(grep -c 'systemctl --user disable' "$LOG" || true)" ]]
rm "$STATE/install.env"

"$ROOT/hermesui/installer/setup.sh" --mode auto \
  --account-id account --zone-id zone --hostname wizard.example.com \
  --allow-email owner@example.com --api-token-file "$STATE/api-token"

grep -qx 'HERMESUI_ACCESS_MODE=cloudflare' "$STATE/install.env"
grep -qx 'HERMESUI_HOSTNAME=wizard.example.com' "$STATE/install.env"
grep -q 'HERMES_WEBUI_HOST=127.0.0.1' "$SYSTEMD/hermesui.service"
grep -q 'HERMES_WEBUI_CSP_FRAME_EXTRA=https://www.aiwizards.com' "$SYSTEMD/hermesui.service"
grep -q -- '--token-file' "$SYSTEMD/hermesui-cloudflared.service"
if grep -q 'fake-connector-token' "$SYSTEMD/hermesui-cloudflared.service"; then
  printf 'Connector secret leaked into the systemd unit.\n' >&2
  exit 1
fi
export HERMESUI_QA_GATE_MODE=generic403
if "$ROOT/hermesui/installer/cloudflare-status.sh" >"$TMP/status403.out" 2>"$TMP/status403.err"; then
  printf 'Status incorrectly accepted a generic provider 403 as proof of Cloudflare Access.\n' >&2
  exit 1
fi
grep -q 'does not prove Cloudflare Access' "$TMP/status403.err"
unset HERMESUI_QA_GATE_MODE
"$ROOT/hermesui/installer/cloudflare-status.sh" | grep -q 'Wizard App URL: https://wizard.example.com/'
export HERMESUI_QA_FAIL_APP_DISABLE_ONCE="$TMP/app-disable-failed"
if "$ROOT/hermesui/installer/cloudflare-uninstall.sh" --api-token-file "$STATE/api-token"; then
  printf 'Injected local teardown failure unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q 'provider_resources_removed' "$STATE/cloudflare.json"
[[ -e "$STATE/install.env" && -e "$STATE/cloudflare.json" && -e "$STATE/cloudflared.token" ]]
[[ -e "$SYSTEMD/hermesui.service" && -e "$SYSTEMD/hermesui-cloudflared.service" ]]
unset HERMESUI_QA_FAIL_APP_DISABLE_ONCE
"$ROOT/hermesui/installer/cloudflare-uninstall.sh" --api-token-file "$STATE/api-token"
[[ ! -e "$STATE/install.env" && ! -e "$STATE/cloudflare.json" && ! -e "$STATE/cloudflared.token" ]]
[[ ! -e "$SYSTEMD/hermesui.service" && ! -e "$SYSTEMD/hermesui-cloudflared.service" ]]
grep -q 'provision apply' "$LOG"
grep -q 'provision cleanup' "$LOG"

# Auto mode preserves an existing legacy/Tailscale install instead of creating
# a competing Cloudflare route.
printf 'HERMESUI_STATE_VERSION=2\nHERMESUI_PORT=8793\n' >"$STATE/install.env"
"$ROOT/hermesui/installer/setup.sh"
grep -q 'tailnet-setup' "$LOG"
rm -f "$STATE/install.env"
"$ROOT/hermesui/installer/setup.sh" --mode tailscale
grep -q 'tailnet-prereq' "$LOG"

printf 'Cloudflare-first setup/status/uninstall and Tailscale-preservation smoke passed.\n'
