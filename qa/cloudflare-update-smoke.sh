#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
server_pid=''
cleanup() {
  if [[ -n "$server_pid" ]]; then kill "$server_pid" >/dev/null 2>&1 || true; fi
  if [[ "${KEEP_QA_TMP:-0}" == 1 ]]; then
    printf 'Preserved QA directory: %s\n' "$TMP" >&2
  else
    rm -rf "$TMP"
  fi
}
trap cleanup EXIT

HOME_DIR="$TMP/home"
WORK="$TMP/work"
ORIGIN="$TMP/origin.git"
STATE_DIR="$HOME_DIR/.config/hermesui"
SYSTEMD_DIR="$HOME_DIR/.config/systemd/user"
SYSTEMCTL_STATE="$TMP/systemctl-state"
SYSTEMCTL_PID="$TMP/systemctl-pid"
PID_COUNTER="$TMP/pid-counter"
FAIL_NEXT_START="$TMP/fail-next-start"
STOP_LOG="$TMP/stop.log"
PORT=18994
mkdir -p "$HOME_DIR/.hermes" "$STATE_DIR" "$SYSTEMD_DIR" "$WORK"
printf 'preserve-me\n' >"$HOME_DIR/.hermes/sentinel"
printf 'active\n' >"$SYSTEMCTL_STATE"
printf '2001\n' >"$SYSTEMCTL_PID"
printf '2001\n' >"$PID_COUNTER"
printf 'token\n' >"$STATE_DIR/cloudflared.token"
printf 'unit\n' >"$SYSTEMD_DIR/hermesui.service"
printf 'unit\n' >"$SYSTEMD_DIR/hermesui-cloudflared.service"
printf 'HERMESUI_STATE_VERSION=3\nHERMESUI_MODE=standalone\nHERMESUI_ACCESS_MODE=cloudflare\nHERMESUI_PROFILE=default\nHERMESUI_HERMES_HOME=%s\nHERMESUI_PORT=%s\nHERMESUI_HOSTNAME=wizard.example.com\n' \
  "$HOME_DIR/.hermes" "$PORT" >"$STATE_DIR/install.env"

cat >"$TMP/systemctl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  "--user is-enabled hermesui.service"|"--user is-enabled hermesui-cloudflared.service") exit 0 ;;
  "--user is-active hermesui.service") [[ "$(cat "$QA_SYSTEMCTL_STATE")" == active ]] ;;
  "--user is-active hermesui-cloudflared.service") exit 0 ;;
  "--user daemon-reload") exit 0 ;;
  "--user show hermesui.service --property=MainPID --value")
    if [[ "$(cat "$QA_SYSTEMCTL_STATE")" == active ]]; then cat "$QA_SYSTEMCTL_PID"; else printf '0\n'; fi
    ;;
  "--user show hermesui.service --property=ActiveState --value") cat "$QA_SYSTEMCTL_STATE" ;;
  "--user stop hermesui.service") printf 'inactive\n' >"$QA_SYSTEMCTL_STATE"; printf '0\n' >"$QA_SYSTEMCTL_PID" ;;
  "--user start hermesui.service")
    if [[ -e "$QA_FAIL_NEXT_START" ]]; then rm -f "$QA_FAIL_NEXT_START"; exit 23; fi
    printf 'active\n' >"$QA_SYSTEMCTL_STATE"
    current="$(cat "$QA_PID_COUNTER")"
    next="$((current + 1))"
    printf '%s\n' "$next" >"$QA_PID_COUNTER"
    printf '%s\n' "$next" >"$QA_SYSTEMCTL_PID"
    ;;
  *) printf 'unexpected systemctl call: %s\n' "$*" >&2; exit 91 ;;
esac
SH
chmod +x "$TMP/systemctl"

cat >"$TMP/stop-helper.py" <<'PY'
#!/usr/bin/env python3
from pathlib import Path
import os
Path(os.environ["QA_STOP_LOG"]).open("a", encoding="utf-8").write("verified\n")
PY
chmod +x "$TMP/stop-helper.py"

cat >"$TMP/units-helper.py" <<'PY'
#!/usr/bin/env python3
from pathlib import Path
import sys

action = sys.argv[1]
args = dict(zip(sys.argv[2::2], sys.argv[3::2]))
app = Path(args["--app-unit"])
tunnel = Path(args["--tunnel-unit"])
candidate = Path(sys.argv[0]).name.startswith("candidate-")
if action == "write":
    app.write_text("candidate unit\n", encoding="utf-8")
    tunnel.write_text("unit\n", encoding="utf-8")
elif action == "verify":
    expected_app = "candidate unit\n" if candidate else "unit\n"
    if app.read_text(encoding="utf-8") != expected_app:
        raise SystemExit(1)
    if tunnel.read_text(encoding="utf-8") != "unit\n":
        raise SystemExit(1)
else:
    raise SystemExit(2)
PY
chmod +x "$TMP/units-helper.py"

cat >"$TMP/cloudflared" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "$TMP/cloudflared"

python3 - "$PORT" <<'PY' &
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import sys
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_response(404); self.end_headers(); return
        body = json.dumps({"status": "ok", "active_runs": 0, "active_streams": 0}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_args):
        pass
HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
PY
server_pid=$!
for _ in $(seq 1 50); do
  python3 - "$PORT" <<'PY' >/dev/null 2>&1 && break || true
import sys, urllib.request
urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/health", timeout=1).read()
PY
  sleep 0.1
done

mkdir -p "$WORK/hermesui/installer"
git init -q -b main "$WORK"
git -C "$WORK" config user.name 'Wizard App Cloudflare Update QA'
git -C "$WORK" config user.email 'update-qa@example.invalid'
printf 'base\n' >"$WORK/VERSION"
git -C "$WORK" add .
git -C "$WORK" commit -q -m base
base_commit="$(git -C "$WORK" rev-parse HEAD)"
base_tree="$(git -C "$WORK" rev-parse 'HEAD^{tree}')"
git -C "$WORK" switch -q -c release-fixtures
printf 'candidate\n' >"$WORK/VERSION"
git -C "$WORK" add .
git -C "$WORK" commit -q -m candidate
candidate_commit="$(git -C "$WORK" rev-parse HEAD)"
git -C "$WORK" tag -a v9.9.8 -m 'successful fixture'
git -C "$WORK" tag -a v9.9.9 -m 'failing-start fixture'
git -C "$WORK" switch -q main
git clone -q --bare "$WORK" "$ORIGIN"
git -C "$WORK" remote add origin "$ORIGIN"

export HOME="$HOME_DIR"
export HERMESUI_REPO_ROOT_OVERRIDE="$WORK"
export HERMESUI_STATE_DIR="$STATE_DIR"
export HERMESUI_SYSTEMD_DIR="$SYSTEMD_DIR"
export HERMESUI_SYSTEMCTL="$TMP/systemctl"
export HERMESUI_PYTHON="$(command -v python3)"
export HERMESUI_CLOUDFLARED="$TMP/cloudflared"
export HERMESUI_PROCESS_STOP="$TMP/stop-helper.py"
export HERMESUI_CLOUDFLARE_UNITS_HELPER="$TMP/units-helper.py"
export HERMESUI_CLOUDFLARE_BASELINE_UNITS_HELPER="$TMP/units-helper.py"
export HERMESUI_LIFECYCLE_LOCK_FILE="$TMP/lifecycle.lock"
export QA_SYSTEMCTL_STATE="$SYSTEMCTL_STATE"
export QA_SYSTEMCTL_PID="$SYSTEMCTL_PID"
export QA_PID_COUNTER="$PID_COUNTER"
export QA_FAIL_NEXT_START="$FAIL_NEXT_START"
export QA_STOP_LOG="$STOP_LOG"

# A candidate start failure must restore the exact baseline checkout/runtime and
# leave the Hermes home untouched.
: >"$FAIL_NEXT_START"
if "$ROOT/hermesui/installer/update.sh" v9.9.9 "$candidate_commit" >"$TMP/failure.out" 2>"$TMP/failure.err"; then
  printf 'Cloudflare update failure fixture unexpectedly succeeded.\n' >&2
  exit 1
else
  status=$?
fi
[[ "$status" == 23 ]]
[[ "$(git -C "$WORK" symbolic-ref --short HEAD)" == main ]]
[[ "$(git -C "$WORK" rev-parse HEAD)" == "$base_commit" ]]
[[ "$(git -C "$WORK" rev-parse 'HEAD^{tree}')" == "$base_tree" ]]
[[ "$(cat "$SYSTEMCTL_STATE")" == active ]]
[[ "$(cat "$HOME_DIR/.hermes/sentinel")" == preserve-me ]]
[[ "$(cat "$SYSTEMD_DIR/hermesui.service")" == unit ]]
[[ "$(cat "$SYSTEMD_DIR/hermesui-cloudflared.service")" == unit ]]
grep -q 'restored the previous checkout and exact active Wizard App runtime state' "$TMP/failure.err"

# A successful update must detach at the reviewed commit, replace only the app
# process, and preserve all Hermes state bytes.
printf 'active\n' >"$SYSTEMCTL_STATE"
printf '3001\n' >"$SYSTEMCTL_PID"
"$ROOT/hermesui/installer/update.sh" v9.9.8 "$candidate_commit" >"$TMP/success.out" 2>"$TMP/success.err"
if git -C "$WORK" symbolic-ref --quiet HEAD >/dev/null; then
  printf 'Expected a detached candidate checkout.\n' >&2
  exit 1
fi
[[ "$(git -C "$WORK" rev-parse HEAD)" == "$candidate_commit" ]]
[[ "$(cat "$WORK/VERSION")" == candidate ]]
[[ "$(cat "$SYSTEMCTL_STATE")" == active ]]
[[ "$(cat "$HOME_DIR/.hermes/sentinel")" == preserve-me ]]
[[ "$(cat "$SYSTEMD_DIR/hermesui.service")" == 'candidate unit' ]]
[[ "$(cat "$SYSTEMD_DIR/hermesui-cloudflared.service")" == unit ]]
[[ "$(wc -l <"$STOP_LOG")" -ge 3 ]]
grep -q 'Hermes home .* was preserved' "$TMP/success.out"

printf 'Cloudflare managed-install replacement, exact rollback, and Hermes-home preservation tests passed.\n'
