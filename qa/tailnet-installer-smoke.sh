#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
SERVER_PID=""
CROSS_TMP=""
cleanup() {
  [[ -z "$SERVER_PID" ]] || kill "$SERVER_PID" >/dev/null 2>&1 || true
  [[ -z "$CROSS_TMP" ]] || rm -rf "$CROSS_TMP"
  if [[ "${HERMESUI_QA_KEEP_TMP:-0}" == "1" ]]; then
    printf 'Preserved Tailnet QA directory: %s\n' "$TMP" >&2
  else
    rm -rf "$TMP"
  fi
}
trap cleanup EXIT
mkdir -p "$TMP/home" "$TMP/bin" "$TMP/systemd" "$TMP/state"
LOG="$TMP/calls.log"
ROUTE_STATE="$TMP/route-owned"
ROUTE_FOREIGN_STATE="$TMP/route-foreign"
SERVICE_STATE="$TMP/service-active"
STOPPED_STATE="$TMP/service-stopped"
ENABLE_LINK="$TMP/systemd/default.target.wants/hermesui-launcher.service"

cat >"$TMP/bin/systemctl" <<'SH'
#!/usr/bin/env bash
printf 'systemctl %s\n' "$*" >>"$HERMESUI_QA_LOG"
case " $* " in
  *" daemon-reload "*)
    [[ "${HERMESUI_QA_SYSTEMCTL_FAIL:-}" != "daemon-reload" ]] || exit 1
    if [[ -e "$HERMESUI_QA_UNIT_FILE" ]]; then
      : >"$HERMESUI_QA_SYSTEMD_CACHE"
    else
      rm -f "$HERMESUI_QA_SYSTEMD_CACHE"
    fi
    if [[ "${HERMESUI_QA_SETUP_UNIT_RACE:-}" == "after_daemon_reload" ]]; then
      printf '[Unit]\nDescription=Foreign takeover after daemon reload\n' >"$HERMESUI_QA_UNIT_FILE"
    fi
    ;;

  *" is-enabled "*)
    if [[ -L "$HERMESUI_QA_ENABLE_LINK" ]]; then printf 'enabled\n'; else exit 1; fi
    ;;
  *" is-active "*)
    if [[ -e "$HERMESUI_QA_STOPPED_STATE" ]]; then exit 3; fi
    if [[ -e "$HERMESUI_QA_SERVICE_STATE" || -e "$HERMESUI_QA_FOREIGN_ACTIVE" || "${HERMESUI_QA_ACTIVE:-0}" == "1" ]]; then printf 'active\n'; else exit 3; fi
    ;;
  *" --property=ActiveState --property=LoadState --property=MainPID "*)
    [[ "${HERMESUI_QA_SYSTEMCTL_FAIL:-}" != "service-state" ]] || exit 79
    [[ -z "${HERMESUI_QA_STOP_QUERY_FAIL_FLAG:-}" || ! -e "$HERMESUI_QA_STOP_QUERY_FAIL_FLAG" ]] || exit 79
    if [[ -e "$HERMESUI_QA_STOPPED_STATE" ]]; then
      printf 'ActiveState=inactive\nLoadState=not-found\nMainPID=0\n'
    elif [[ -e "$HERMESUI_QA_SERVICE_STATE" || -e "$HERMESUI_QA_FOREIGN_ACTIVE" || "${HERMESUI_QA_ACTIVE:-0}" == "1" ]]; then
      printf 'ActiveState=active\nLoadState=loaded\nMainPID=424242\n'
    else
      printf 'ActiveState=inactive\nLoadState=not-found\nMainPID=0\n'
    fi
    ;;
  *" --property=ActiveState --value "*)
    [[ "${HERMESUI_QA_SYSTEMCTL_FAIL:-}" != "active-state" ]] || exit 78
    if [[ -e "$HERMESUI_QA_STOPPED_STATE" ]]; then
      printf 'inactive\n'
    elif [[ -e "$HERMESUI_QA_SERVICE_STATE" || -e "$HERMESUI_QA_FOREIGN_ACTIVE" || "${HERMESUI_QA_ACTIVE:-0}" == "1" ]]; then
      printf 'active\n'
    else
      printf 'inactive\n'
    fi
    ;;
  *" --property=MainPID --value "*)
    [[ "${HERMESUI_QA_SYSTEMCTL_FAIL:-}" != "main-pid" ]] || exit 77
    if [[ -e "$HERMESUI_QA_STOPPED_STATE" ]]; then
      printf '0\n'
    elif [[ -e "$HERMESUI_QA_SERVICE_STATE" || -e "$HERMESUI_QA_FOREIGN_ACTIVE" || "${HERMESUI_QA_ACTIVE:-0}" == "1" ]]; then
      printf '424242\n'
    else
      printf '0\n'
    fi
    ;;
  *" --property=FragmentPath --value "*)
    [[ "${HERMESUI_QA_SYSTEMCTL_FAIL:-}" != "show" ]] || exit 76
    if [[ -e "$HERMESUI_QA_UNIT_FILE" || -e "$HERMESUI_QA_SYSTEMD_CACHE" ]]; then
      [[ -z "${HERMESUI_QA_FRAGMENT:-}" ]] || printf '%s\n' "$HERMESUI_QA_FRAGMENT"
    fi
    ;;
  *" --property=LoadState --value "*)
    [[ "${HERMESUI_QA_SYSTEMCTL_FAIL:-}" != "show-load-state" ]] || exit 76
    if [[ " $* " == *" hermesui.service "* ]]; then
      if [[ -e "$HERMESUI_QA_STOPPED_STATE" ]]; then
        printf 'not-found\n'
      elif [[ -e "$HERMESUI_QA_SERVICE_STATE" || -e "$HERMESUI_QA_FOREIGN_ACTIVE" || "${HERMESUI_QA_ACTIVE:-0}" == "1" ]]; then
        printf 'loaded\n'
      else
        printf 'not-found\n'
      fi
    elif [[ -e "$HERMESUI_QA_UNIT_FILE" || -e "$HERMESUI_QA_SYSTEMD_CACHE" ]]; then
      printf 'loaded\n'
    else
      printf 'not-found\n'
    fi
    ;;
esac
SH

cat >"$TMP/bin/stop-owned-process" <<'SH'
#!/usr/bin/env bash
printf 'stop-owned-process %s\n' "$*" >>"$HERMESUI_QA_LOG"
[[ "${HERMESUI_QA_SYSTEMCTL_FAIL:-}" != "stop" ]] || exit 1
[[ ! -e "$HERMESUI_QA_FOREIGN_ACTIVE" ]] || exit 75
[[ " $* " != *" --verify-only "* ]] || exit 0
if [[ "${HERMESUI_QA_PROCESS_ENTRY_TAKEOVER:-0}" == "1" ]]; then
  printf '[Unit]\nDescription=Foreign takeover at process-stop entry\n' >"$HERMESUI_QA_UNIT_FILE"
  : >"$HERMESUI_QA_FOREIGN_ACTIVE"
  exit 75
fi
if [[ "${HERMESUI_QA_UNINSTALL_ROUTE_RACE:-0}" == "1" ]]; then
  rm -f "$HERMESUI_QA_ROUTE_STATE"
  : >"$HERMESUI_QA_ROUTE_FOREIGN_STATE"
fi
if [[ "${HERMESUI_QA_UNINSTALL_UNIT_STOP_RACE:-0}" == "1" ]]; then
  printf '[Unit]\nDescription=Foreign takeover after owned process stop\n' >"$HERMESUI_QA_UNIT_FILE"
fi
if [[ "${HERMESUI_QA_UNINSTALL_STATE_RACE:-0}" == "1" ]]; then
  printf 'FOREIGN_STATE=1\n' >"$HERMESUI_QA_STATE_FILE"
fi
rm -f "$HERMESUI_QA_SERVICE_STATE"
: >"$HERMESUI_QA_STOPPED_STATE"
SH

cat >"$TMP/bin/start-owned-service" <<'SH'
#!/usr/bin/env bash
printf 'start-owned-service %s\n' "$*" >>"$HERMESUI_QA_LOG"
[[ "${HERMESUI_QA_SYSTEMCTL_FAIL:-}" != "service-start" ]] || exit 1
if [[ "${HERMESUI_QA_SETUP_UNIT_RACE:-}" == "service_start_entry" ]]; then
  printf '[Unit]\nDescription=Foreign takeover at transient service start\n' >"$HERMESUI_QA_UNIT_FILE"
fi
if [[ "${HERMESUI_QA_RUNTIME_COLLISION:-0}" == "1" ]]; then
  : >"$HERMESUI_QA_FOREIGN_ACTIVE"
  exit 75
fi
rm -f "$HERMESUI_QA_STOPPED_STATE"
: >"$HERMESUI_QA_SERVICE_STATE"
SH

cat >"$TMP/bin/runtime-home-guard" <<'PY'
#!/usr/bin/env python3
import os
import sys
from pathlib import Path

with Path(os.environ["HERMESUI_QA_LOG"]).open("a", encoding="utf-8") as handle:
    handle.write("runtime-home-guard " + " ".join(sys.argv[1:]) + "\n")

command = sys.argv[1] if len(sys.argv) > 1 else ""
if command == "normalize" and len(sys.argv) == 3:
    print(Path(sys.argv[2]).expanduser().resolve(strict=False))
elif command == "check":
    if os.environ.get("HERMESUI_QA_RUNTIME_HOME_CONFLICT", "0") == "1":
        print(
            "ERROR: refusing to start a second Hermes/WebUI execution backend "
            "over the requested HERMES_HOME.",
            file=sys.stderr,
        )
        raise SystemExit(1)
else:
    raise SystemExit(2)
PY

cat >"$TMP/bin/tailscale" <<'SH'
#!/usr/bin/env bash
printf 'tailscale %s\n' "$*" >>"$HERMESUI_QA_LOG"
if [[ "${HERMESUI_QA_TAILSCALE_STATUS_FAIL:-0}" == "1" && "$*" == "status" ]]; then
  exit 1
elif [[ " $* " == *" status --self --json "* ]]; then
  printf '{"Self":{"DNSName":"device.tailnet.example.ts.net."}}\n'
elif [[ " $* " == *" serve status --json "* ]]; then
  if [[ "${HERMESUI_QA_UNINSTALL_UNIT_RACE:-0}" == "1" && ! -e "${HERMESUI_QA_UNIT_RACE_DONE:-}" ]]; then
    printf '[Unit]\nDescription=Foreign takeover before disable\n' >"$HERMESUI_QA_UNIT_FILE"
    : >"$HERMESUI_QA_UNIT_RACE_DONE"
  fi
  if [[ -e "${HERMESUI_QA_ROUTE_FOREIGN_STATE:-}" ]]; then
    printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:7777/hermesUI"}}}}}\n'
    exit 0
  fi
  mode="${HERMESUI_QA_SERVE_MODE:-missing}"
  case "$mode" in
    missing)
      if [[ -e "$HERMESUI_QA_ROUTE_STATE" ]]; then
        printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:18993"}}}}}\n'
      else
        printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{}}}}\n'
      fi
      ;;
    owned)
      if [[ -e "$HERMESUI_QA_ROUTE_STATE" ]]; then
        printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:18993"}}}}}\n'
      else
        printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{}}}}\n'
      fi
      ;;
    manual_owned) printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:18993/hermesUI"}}}}}\n' ;;
    foreign) printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:7777/hermesUI"}}}}}\n' ;;
    foreground_foreign) printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{}}},"Foreground":{"session-1":{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:7777/hermesUI"}}}}}}}\n' ;;
    foreground_owned) printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{}}},"Foreground":{"session-1":{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:18993/hermesUI"}}}}}}}\n' ;;
    mixed_owned) printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:18993/hermesUI"}}}},"Foreground":{"session-1":{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:18993/hermesUI"}}}}}}}\n' ;;
    mixed_foreign) printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:18993/hermesUI"}}}},"Foreground":{"session-1":{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:7777/hermesUI"}}}}}}}\n' ;;
    wrong_listener) printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:18993"}}},"device.tailnet.example.ts.net:8443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:18993/hermesUI"}}}}}\n' ;;
    wrong_then_owned)
      if [[ -e "$HERMESUI_QA_ROUTE_STATE" ]]; then
        printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:18993"}}},"device.tailnet.example.ts.net:8443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:18993/hermesUI"}}}}}\n'
      else
        printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:18993"}}},"device.tailnet.example.ts.net:8443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:18993/hermesUI"}}}}}\n'
      fi
      ;;
    post_stuck)
      if [[ -e "$HERMESUI_QA_ROUTE_STATE" ]]; then
        printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:18993"}}}}}\n'
      else
        printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{}}},"Foreground":{"session-1":{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/hermesUI":{"Proxy":"http://127.0.0.1:18993/hermesUI"}}}}}}}\n'
      fi
      ;;
    funnel) printf '{"AllowFunnel":{"device.tailnet.example.ts.net:443":true},"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{}}}}\n' ;;
    listener_null) printf '{"Web":{"device.tailnet.example.ts.net:443":null}}\n' ;;
    handler_null) printf '{"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{"/hermesUI":null}}}}\n' ;;
    foreground_listener_null) printf '{"Web":{},"Foreground":{"session-1":{"Web":{"device.tailnet.example.ts.net:443":null}}}}\n' ;;
    tcp_null) printf '{"TCP":{"443":null},"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{}}}}\n' ;;
    tcp_future) printf '{"TCP":{"443":{"HTTPS":true,"Future":true}},"Web":{"device.tailnet.example.ts.net:443":{"Handlers":{}}}}\n' ;;
  esac
elif [[ " $* " == *" serve --bg "* ]]; then
  : >"$HERMESUI_QA_ROUTE_STATE"
  [[ "${HERMESUI_QA_TAILSCALE_SERVE_FAIL:-0}" != "1" ]] || exit 42
elif [[ " $* " == *" serve --https=443 --set-path=/hermesUI off "* ]]; then
  [[ "${HERMESUI_QA_TAILSCALE_OFF_FAIL:-0}" != "1" ]] || exit 1
  rm -f "$HERMESUI_QA_ROUTE_STATE"
fi
SH

cat >"$TMP/bin/curl" <<'SH'
#!/usr/bin/env bash
printf 'curl %s\n' "$*" >>"$HERMESUI_QA_LOG"
if [[ "${HERMESUI_QA_TAILNET_HEALTH_FAIL:-0}" == "1" && "$*" == *"https://device.tailnet.example.ts.net/hermesUI/health"* ]]; then
  [[ -z "${HERMESUI_QA_ROLLBACK_FUNNEL_FLAG:-}" ]] || : >"$HERMESUI_QA_ROLLBACK_FUNNEL_FLAG"
  [[ -z "${HERMESUI_QA_STOP_QUERY_FAIL_FLAG:-}" ]] || : >"$HERMESUI_QA_STOP_QUERY_FAIL_FLAG"
  case "${HERMESUI_QA_ROLLBACK_RACE:-}" in
    route) : >"$HERMESUI_QA_ROUTE_FOREIGN_STATE" ;;
    unit) printf '[Unit]\nDescription=Foreign takeover\n' >"$HERMESUI_QA_UNIT_FILE" ;;
    state) printf 'FOREIGN_STATE=1\n' >"$HERMESUI_QA_STATE_FILE" ;;
  esac
  exit 22
fi
if [[ "${HERMESUI_QA_PASSWORD_ROOT_BLOCK:-0}" == "1" && "$*" == *"https://device.tailnet.example.ts.net/hermesUI/" && "$*" != *"/health"* && "$*" != *"manifest.json"* ]]; then
  exit 22
fi
if [[ "$*" == *"manifest.json"* ]]; then
  printf '{"name":"HermesUI","id":"./","start_url":"./?source=pwa","scope":"./"}\n'
elif [[ "$*" == *"https://device.tailnet.example.ts.net/hermesUI/"* && "$*" != *"/health"* ]]; then
  printf '<!doctype html><title>HermesUI</title>\n'
else
  printf '{"status":"healthy"}\n'
fi
SH

cat >"$TMP/bin/sleep" <<'SH'
#!/usr/bin/env bash
exit 0
SH

cat >"$TMP/bin/hermes" <<'SH'
#!/usr/bin/env bash
[[ "${1:-}" == "--version" ]] && { printf 'Hermes 0.0-test\n'; exit 0; }
exit 1
SH

cat >"$TMP/bin/hermesui-rm" <<'SH'
#!/usr/bin/env bash
if [[ "${HERMESUI_QA_RM_FAIL:-}" == "unit" && "$*" == *"hermesui-launcher.service"* ]]; then
  exit 1
fi
exec /usr/bin/rm "$@"
SH

cat >"$TMP/bin/path-op" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
command="${1:-}"
destination=''
case "$command" in
  publish) destination="${3:-}" ;;
  remove) destination="${2:-}" ;;
  symlink-create) destination="${3:-}" ;;
  symlink-remove) destination="${2:-}" ;;
esac
case "${HERMESUI_QA_PATH_RACE:-}" in
  setup_state) [[ "$command" != "publish" || "$destination" != "$HERMESUI_QA_STATE_FILE" ]] || printf 'FOREIGN_STATE=1\n' >"$destination" ;;
  setup_unit) [[ "$command" != "publish" || "$destination" != "$HERMESUI_QA_UNIT_FILE" ]] || printf '[Unit]\nDescription=Foreign setup takeover\n' >"$destination" ;;
  setup_enable_link) [[ "$command" != "symlink-create" || "$destination" != "$HERMESUI_QA_ENABLE_LINK" ]] || ln -s /foreign/unit "$destination" ;;
  setup_enable_unit_takeover) [[ "$command" != "symlink-create" || "$destination" != "$HERMESUI_QA_ENABLE_LINK" ]] || printf '[Unit]\nDescription=Foreign unit at link-create entry\n' >"$HERMESUI_QA_UNIT_FILE" ;;
  uninstall_enable_link) [[ "$command" != "symlink-remove" || "$destination" != "$HERMESUI_QA_ENABLE_LINK" ]] || { rm -f "$destination"; ln -s /foreign/unit "$destination"; } ;;
  uninstall_enable_unit_takeover) [[ "$command" != "symlink-remove" || "$destination" != "$HERMESUI_QA_ENABLE_LINK" ]] || printf '[Unit]\nDescription=Foreign unit at link-remove entry\n' >"$HERMESUI_QA_UNIT_FILE" ;;
  uninstall_unit_rm) [[ "$command" != "remove" || "$destination" != "$HERMESUI_QA_UNIT_FILE" ]] || printf '[Unit]\nDescription=Foreign removal takeover\n' >"$destination" ;;
  uninstall_state_rm) [[ "$command" != "remove" || "$destination" != "$HERMESUI_QA_STATE_FILE" ]] || printf 'FOREIGN_STATE=1\n' >"$destination" ;;
esac
if [[ "$command" == "remove" && "${HERMESUI_QA_RM_FAIL:-}" == "unit" && "$destination" == "$HERMESUI_QA_UNIT_FILE" ]]; then
  exit 1
fi
exec "$HERMESUI_QA_REAL_PATH_OP" "$@"
SH

cat >"$TMP/bin/serve-cas" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
expected=''
desired=''
while (($#)); do
  case "$1" in
    --expected) expected="$2"; shift 2 ;;
    --desired) desired="$2"; shift 2 ;;
    *) shift ;;
  esac
done
if [[ "${HERMESUI_QA_CAS_ROUTE_RACE:-0}" == "1" ]]; then
  rm -f "$HERMESUI_QA_ROUTE_STATE"
  : >"$HERMESUI_QA_ROUTE_FOREIGN_STATE"
fi
if [[ -e "$HERMESUI_QA_ROUTE_FOREIGN_STATE" ]]; then
  current='http://127.0.0.1:7777/hermesUI'
elif [[ -e "$HERMESUI_QA_ROUTE_STATE" ]]; then
  current="http://127.0.0.1:${HERMESUI_PORT:-18993}"
else
  current='absent'
fi
[[ "$current" == "$expected" ]] || exit 75
if [[ -n "${HERMESUI_QA_ROLLBACK_FUNNEL_FLAG:-}" && -e "$HERMESUI_QA_ROLLBACK_FUNNEL_FLAG" && "$desired" != "absent" ]]; then
  exit 75
fi
if [[ "${HERMESUI_QA_CAS_FUNNEL_RACE:-0}" == "1" && "$desired" != "absent" ]]; then
  exit 75
fi
if [[ "$desired" == "absent" ]]; then
  printf '%s\n' 'tailscale serve --https=443 --set-path=/hermesUI off' >>"$HERMESUI_QA_LOG"
  [[ "${HERMESUI_QA_TAILSCALE_OFF_FAIL:-0}" != "1" ]] || exit 1
  rm -f "$HERMESUI_QA_ROUTE_STATE" "$HERMESUI_QA_ROUTE_FOREIGN_STATE"
else
  printf 'tailscale serve --bg --https=443 --set-path=/hermesUI %s\n' "$desired" >>"$HERMESUI_QA_LOG"
  rm -f "$HERMESUI_QA_ROUTE_FOREIGN_STATE"
  : >"$HERMESUI_QA_ROUTE_STATE"
  [[ "${HERMESUI_QA_TAILSCALE_SERVE_FAIL:-0}" != "1" ]] || exit 42
fi
SH

chmod +x "$TMP/bin/systemctl" "$TMP/bin/stop-owned-process" "$TMP/bin/start-owned-service" "$TMP/bin/runtime-home-guard" "$TMP/bin/tailscale" "$TMP/bin/curl" "$TMP/bin/hermes" "$TMP/bin/hermesui-rm" "$TMP/bin/path-op" "$TMP/bin/serve-cas" "$TMP/bin/sleep"

export HOME="$TMP/home"
export HERMES_HOME="$TMP/home/.hermes"
export PATH="$TMP/bin:$PATH"
export HERMESUI_QA_LOG="$LOG"
export HERMESUI_QA_ROUTE_STATE="$ROUTE_STATE"
export HERMESUI_QA_ROUTE_FOREIGN_STATE="$ROUTE_FOREIGN_STATE"
export HERMESUI_QA_SERVICE_STATE="$SERVICE_STATE"
export HERMESUI_QA_STOPPED_STATE="$STOPPED_STATE"
export HERMESUI_SKIP_PREREQS=1
export HERMESUI_SYSTEMD_DIR="$TMP/systemd"
export HERMESUI_STATE_DIR="$TMP/state"
export HERMESUI_SYSTEMCTL="$TMP/bin/systemctl"
export HERMESUI_SYSTEMD_ANALYZE=systemd-analyze
export HERMESUI_TAILSCALE="$TMP/bin/tailscale"
export HERMESUI_CURL="$TMP/bin/curl"
export HERMESUI_RM="$TMP/bin/hermesui-rm"
export HERMESUI_QA_FRAGMENT="$TMP/systemd/hermesui-launcher.service"
export HERMESUI_QA_UNIT_FILE="$TMP/systemd/hermesui-launcher.service"
export HERMESUI_QA_ENABLE_LINK="$ENABLE_LINK"
export HERMESUI_QA_FOREIGN_ACTIVE="$TMP/foreign-active"
export HERMESUI_QA_STATE_FILE="$TMP/state/install.env"
export HERMESUI_QA_SYSTEMD_CACHE="$TMP/systemd-cache"
export HERMESUI_QA_UNIT_RACE_DONE="$TMP/uninstall-unit-race-done"
export HERMESUI_QA_REAL_PATH_OP="$ROOT/hermesui/installer/owned-path-op.py"
export HERMESUI_PATH_OP="$TMP/bin/path-op"
export HERMESUI_PROCESS_STOP="$TMP/bin/stop-owned-process"
export HERMESUI_SERVICE_START="$TMP/bin/start-owned-service"
export HERMESUI_RUNTIME_HOME_GUARD="$TMP/bin/runtime-home-guard"
export HERMESUI_SERVE_CAS_HELPER="$TMP/bin/serve-cas"
export HERMESUI_LIFECYCLE_LOCK_FILE="$TMP/lifecycle.lock"
export HERMESUI_QA_PASSWORD_ROOT_BLOCK=1

# A concurrent lifecycle owner must block setup before any preflight or
# mutation. This exercises the same lock shared by setup, update, and uninstall.
exec 8>"$HERMESUI_LIFECYCLE_LOCK_FILE"
chmod 600 "$HERMESUI_LIFECYCLE_LOCK_FILE"
flock -n 8
export HERMESUI_PORT=18993 HERMESUI_QA_ACTIVE=0 HERMESUI_QA_SERVE_MODE=missing
set +e
"$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/lock-contention.out" 2>"$TMP/lock-contention.err"
lock_status=$?
set -e
flock -u 8
exec 8>&-
[[ "$lock_status" == "75" ]]
[[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$TMP/state/install.env" && ! -e "$ROUTE_STATE" && ! -e "$SERVICE_STATE" ]]
grep -q 'another HermesUI setup, update, or uninstall is already running' "$TMP/lock-contention.err"

# Unsupported client-only or isolated modes fail before any local or Tailnet
# discovery/mutation. Wizard App intentionally supports standalone only.
for unsupported_mode in external isolated; do
  : >"$LOG"
  export HERMESUI_MODE="$unsupported_mode"
  if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/mode-${unsupported_mode}.out" 2>"$TMP/mode-${unsupported_mode}.err"; then
    printf '%s mode unexpectedly succeeded.\n' "$unsupported_mode" >&2
    exit 1
  fi
  [[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$TMP/state/install.env" && ! -e "$ROUTE_STATE" && ! -e "$SERVICE_STATE" ]]
  [[ ! -s "$LOG" ]]
  grep -Eq 'not supported safely|not yet supported' "$TMP/mode-${unsupported_mode}.err"
done
unset HERMESUI_MODE

# A same-home execution backend must stop standalone setup before any managed
# state, service, or route is created. Choosing another port is not offered.
: >"$LOG"
export HERMESUI_QA_RUNTIME_HOME_CONFLICT=1
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/runtime-home-conflict.out" 2>"$TMP/runtime-home-conflict.err"; then
  printf 'Shared runtime-home conflict unexpectedly succeeded.\n' >&2
  exit 1
fi
unset HERMESUI_QA_RUNTIME_HOME_CONFLICT
[[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$TMP/state/install.env" && ! -e "$ROUTE_STATE" && ! -e "$SERVICE_STATE" ]]
grep -q 'refusing to start a second Hermes/WebUI execution backend' "$TMP/runtime-home-conflict.err"
if grep -qi 'choose another port' "$TMP/runtime-home-conflict.err"; then
  printf 'Shared runtime-home conflict incorrectly suggested another port.\n' >&2
  exit 1
fi
: >"$LOG"

# A failed Tailscale prerequisite must not execute the suggested state-changing command.
export HERMESUI_QA_TAILSCALE_STATUS_FAIL=1
if "$ROOT/hermesui/installer/tailnet-prereq-check.sh" >"$TMP/prereq.out" 2>"$TMP/prereq.err"; then
  printf 'Disconnected prerequisite test unexpectedly succeeded.\n' >&2
  exit 1
fi
unset HERMESUI_QA_TAILSCALE_STATUS_FAIL
python3 - "$LOG" <<'PY'
from pathlib import Path
import sys
log = Path(sys.argv[1]).read_text(encoding='utf-8')
assert 'tailscale status\n' in log
assert 'tailscale up' not in log
PY
: >"$LOG"

# A failed authoritative runtime-state query is not evidence that the service
# is inactive. Setup must fail before any mutation.
export HERMESUI_PORT=18993 HERMESUI_QA_ACTIVE=0 HERMESUI_QA_SERVE_MODE=missing HERMESUI_QA_SYSTEMCTL_FAIL=service-state
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/service-state-preflight.out" 2>"$TMP/service-state-preflight.err"; then
  printf 'Runtime-state preflight query failure unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$TMP/state/install.env" && ! -e "$SERVICE_STATE" && ! -e "$ROUTE_STATE" ]]
grep -q 'ActiveState, LoadState, and MainPID' "$TMP/service-state-preflight.err"
unset HERMESUI_QA_SYSTEMCTL_FAIL

# A busy unmanaged port must fail before a unit or route is changed.
python3 -m http.server 18994 --bind 127.0.0.1 >/dev/null 2>&1 &
SERVER_PID="$!"
python3 - "$SERVER_PID" <<'PY'
import socket, sys, time
for _ in range(40):
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', 18994)) == 0:
            break
    time.sleep(0.05)
else:
    raise SystemExit('test server did not start')
PY
export HERMESUI_PORT=18994 HERMESUI_QA_ACTIVE=0
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/port.out" 2>"$TMP/port.err"; then
  printf 'Port collision test unexpectedly succeeded.\n' >&2
  exit 1
fi
kill "$SERVER_PID"
wait "$SERVER_PID" 2>/dev/null || true
SERVER_PID=""
[[ ! -e "$TMP/systemd/hermesui-launcher.service" ]]

# Setup failures at each systemd mutation boundary must remove fresh state and
# the generated unit without depending on a successfully loaded FragmentPath.
for failure in daemon-reload service-start; do
  rm -f "$ROUTE_STATE" "$ROUTE_FOREIGN_STATE" "$SERVICE_STATE" "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env"
  export HERMESUI_PORT=18993 HERMESUI_QA_ACTIVE=0 HERMESUI_QA_SERVE_MODE=missing HERMESUI_QA_SYSTEMCTL_FAIL="$failure"
  if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/setup-${failure}.out" 2>"$TMP/setup-${failure}.err"; then
    printf '%s setup failure test unexpectedly succeeded.\n' "$failure" >&2
    exit 1
  fi
  [[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$TMP/state/install.env" && ! -e "$SERVICE_STATE" && ! -e "$ROUTE_STATE" ]]
  if [[ "$failure" == "daemon-reload" ]]; then
    grep -q 'automatic rollback was incomplete' "$TMP/setup-${failure}.err"
  else
    grep -q 'failed setup changes were rolled back' "$TMP/setup-${failure}.err"
  fi
done
unset HERMESUI_QA_SYSTEMCTL_FAIL
: >"$LOG"

# Tailscale Serve may install the requested route before returning a failure.
# Rollback must recognize that partial mutation and restore the exact prior state.
rm -f "$ROUTE_STATE" "$ROUTE_FOREIGN_STATE" "$SERVICE_STATE" "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env"
export HERMESUI_PORT=18993 HERMESUI_QA_ACTIVE=0 HERMESUI_QA_SERVE_MODE=missing HERMESUI_QA_TAILSCALE_SERVE_FAIL=1
before_off_count="$(grep -c 'set-path=/hermesUI off' "$LOG" || true)"
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/serve-partial.out" 2>"$TMP/serve-partial.err"; then
  printf 'Partial Serve mutation failure test unexpectedly succeeded.\n' >&2
  exit 1
fi
after_off_count="$(grep -c 'set-path=/hermesUI off' "$LOG" || true)"
[[ "$after_off_count" -eq $((before_off_count + 1)) ]]
[[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$TMP/state/install.env" && ! -e "$SERVICE_STATE" && ! -e "$ROUTE_STATE" ]]
grep -q 'failed setup changes were rolled back' "$TMP/serve-partial.err"
unset HERMESUI_QA_TAILSCALE_SERVE_FAIL
: >"$LOG"

# A foreign user unit must not be overwritten.
printf '[Unit]\nDescription=Unrelated service\n' >"$TMP/systemd/hermesui-launcher.service"
export HERMESUI_PORT=18993 HERMESUI_QA_ACTIVE=0 HERMESUI_QA_SERVE_MODE=missing
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/unit.out" 2>"$TMP/unit.err"; then
  printf 'Unit collision test unexpectedly succeeded.\n' >&2
  exit 1
fi
rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK"

# A managed unit without installer state must not be adopted using a default port.
"$ROOT/hermesui/installer/systemd-launcher-unit.py" write "$TMP/systemd/hermesui-launcher.service" \
  --repo-root "$ROOT" --home "$TMP/home" --host 127.0.0.1 --port 18993
export HERMESUI_PORT=18993 HERMESUI_QA_ACTIVE=0 HERMESUI_QA_SERVE_MODE=missing
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/missing-state.out" 2>"$TMP/missing-state.err"; then
  printf 'Missing install-state ownership test unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ ! -e "$TMP/state/install.env" ]]
rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK"

# A foreign route, ownership-ambiguous matching route, or existing Funnel listener must fail closed.
export HERMESUI_QA_SERVE_MODE=foreign
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/route.out" 2>"$TMP/route.err"; then
  printf 'Serve collision test unexpectedly succeeded.\n' >&2
  exit 1
fi
export HERMESUI_QA_SERVE_MODE=foreground_foreign
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/foreground-route.out" 2>"$TMP/foreground-route.err"; then
  printf 'Foreground Serve collision test unexpectedly succeeded.\n' >&2
  exit 1
fi
for mode in manual_owned foreground_owned mixed_owned; do
  export HERMESUI_QA_SERVE_MODE="$mode"
  if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/setup-${mode}.out" 2>"$TMP/setup-${mode}.err"; then
    printf '%s setup ownership test unexpectedly succeeded.\n' "$mode" >&2
    exit 1
  fi
  [[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$TMP/state/install.env" ]]
done
export HERMESUI_QA_SERVE_MODE=funnel
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/funnel.out" 2>"$TMP/funnel.err"; then
  printf 'Funnel collision test unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$TMP/state/install.env" ]]

# A present-null canonical listener is authoritative unknown state, not absence.
# Reject it at preflight whether it is top-level or nested in Foreground.
for mode in listener_null foreground_listener_null; do
  export HERMESUI_QA_SERVE_MODE="$mode"
  if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/${mode}.out" 2>"$TMP/${mode}.err"; then
    printf '%s listener-null test unexpectedly succeeded.\n' "$mode" >&2
    exit 1
  fi
  grep -q 'listener configuration is invalid' "$TMP/${mode}.err"
  [[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$TMP/state/install.env" && ! -e "$SERVICE_STATE" && ! -e "$ROUTE_STATE" ]]
done

# Present-but-incompatible TCP 443 values must fail before any local mutation.
for mode in tcp_null tcp_future; do
  export HERMESUI_QA_SERVE_MODE="$mode"
  if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/${mode}.out" 2>"$TMP/${mode}.err"; then
    printf '%s TCP ownership test unexpectedly succeeded.\n' "$mode" >&2
    exit 1
  fi
  [[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$TMP/state/install.env" && ! -e "$SERVICE_STATE" && ! -e "$ROUTE_STATE" ]]
done

# Funnel enabled after preflight but before the ETag-protected CAS must fail and
# roll back the already prepared local unit, service, and ownership state.
export HERMESUI_QA_SERVE_MODE=missing HERMESUI_QA_CAS_FUNNEL_RACE=1
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/funnel-race.out" 2>"$TMP/funnel-race.err"; then
  printf 'Funnel CAS race test unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$TMP/state/install.env" && ! -e "$SERVICE_STATE" && ! -e "$ROUTE_STATE" ]]
grep -q 'failed setup changes were rolled back' "$TMP/funnel-race.err"
unset HERMESUI_QA_CAS_FUNNEL_RACE
: >"$LOG"

# Normal setup, active rerun, status, and owned-route uninstall.
rm -f "$ROUTE_STATE"
export HERMESUI_QA_SERVE_MODE=missing HERMESUI_QA_ACTIVE=0
"$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/setup.out"
export HERMESUI_QA_SERVE_MODE=owned HERMESUI_QA_ACTIVE=1
unset HERMESUI_PORT
"$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/rerun.out"
"$ROOT/hermesui/installer/tailnet-status.sh" >"$TMP/status.out"

# Locked updater operations must validate the exact checkout/runtime identity,
# avoid every Tailscale query or mutation, and preserve active/inactive intent.
runtime_commit="$(git -C "$ROOT" rev-parse HEAD)"
runtime_tree="$(git -C "$ROOT" rev-parse 'HEAD^{tree}')"
tailscale_calls_before="$(grep -c '^tailscale ' "$LOG" || true)"
HERMESUI_RUNTIME_OPERATION=probe HERMESUI_EXPECTED_RUNTIME_COMMIT="$runtime_commit" HERMESUI_EXPECTED_RUNTIME_TREE="$runtime_tree" \
  "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/runtime-probe-active.out"
grep -qx active "$TMP/runtime-probe-active.out"

# A runtime-only stop used by update must rerun the shared-home guard at the
# mutation boundary. The verified managed PID is allowed, but another or
# ambiguous same-home backend leaves the managed service active and un-signaled.
stop_calls_before="$(grep 'stop-owned-process --pid' "$LOG" | grep -vc -- '--verify-only' || true)"
export HERMESUI_QA_RUNTIME_HOME_CONFLICT=1
if HERMESUI_RUNTIME_OPERATION=stop HERMESUI_EXPECTED_RUNTIME_COMMIT="$runtime_commit" HERMESUI_EXPECTED_RUNTIME_TREE="$runtime_tree" \
  "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/runtime-stop-conflict.out" 2>"$TMP/runtime-stop-conflict.err"; then
  printf 'Shared-home runtime-only stop conflict unexpectedly succeeded.\n' >&2
  exit 1
fi
unset HERMESUI_QA_RUNTIME_HOME_CONFLICT
stop_calls_after="$(grep 'stop-owned-process --pid' "$LOG" | grep -vc -- '--verify-only' || true)"
[[ "$stop_calls_after" == "$stop_calls_before" && -e "$SERVICE_STATE" ]]
grep -q 'Nothing was stopped' "$TMP/runtime-stop-conflict.err"

HERMESUI_RUNTIME_OPERATION=stop HERMESUI_EXPECTED_RUNTIME_COMMIT="$runtime_commit" HERMESUI_EXPECTED_RUNTIME_TREE="$runtime_tree" \
  "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/runtime-stop.out"
grep -qx inactive "$TMP/runtime-stop.out"
HERMESUI_RUNTIME_OPERATION=probe HERMESUI_EXPECTED_RUNTIME_COMMIT="$runtime_commit" HERMESUI_EXPECTED_RUNTIME_TREE="$runtime_tree" \
  "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/runtime-probe-inactive.out"
grep -qx inactive "$TMP/runtime-probe-inactive.out"
HERMESUI_RUNTIME_OPERATION=ensure-active HERMESUI_EXPECTED_RUNTIME_COMMIT="$runtime_commit" HERMESUI_EXPECTED_RUNTIME_TREE="$runtime_tree" \
  "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/runtime-ensure-active.out"
grep -qx active "$TMP/runtime-ensure-active.out"
tailscale_calls_after="$(grep -c '^tailscale ' "$LOG" || true)"
[[ "$tailscale_calls_after" == "$tailscale_calls_before" ]]

if HERMESUI_RUNTIME_OPERATION=stop HERMESUI_EXPECTED_RUNTIME_COMMIT="$(printf '0%.0s' {1..40})" HERMESUI_EXPECTED_RUNTIME_TREE="$runtime_tree" \
  "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/runtime-wrong-identity.out" 2>"$TMP/runtime-wrong-identity.err"; then
  printf 'Wrong runtime identity unexpectedly authorized a stop.\n' >&2
  exit 1
fi
[[ -e "$SERVICE_STATE" ]]
grep -q 'checkout identity does not match' "$TMP/runtime-wrong-identity.err"

# Status requires authoritative state and a managed unit whose port matches it.
mv "$TMP/state/install.env" "$TMP/state/install.env.saved"
if "$ROOT/hermesui/installer/tailnet-status.sh" >"$TMP/status-missing-state.out" 2>"$TMP/status-missing-state.err"; then
  printf 'Missing status ownership-state test unexpectedly succeeded.\n' >&2
  exit 1
fi
mv "$TMP/state/install.env.saved" "$TMP/state/install.env"
cp "$TMP/systemd/hermesui-launcher.service" "$TMP/systemd/hermesui-launcher.service.saved"
python3 - "$TMP/systemd/hermesui-launcher.service" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
path.write_text(path.read_text().replace('HERMES_WEBUI_PORT=18993', 'HERMES_WEBUI_PORT=18994'), encoding='utf-8')
PY
if "$ROOT/hermesui/installer/tailnet-status.sh" >"$TMP/status-unit-port.out" 2>"$TMP/status-unit-port.err"; then
  printf 'Status unit/state port mismatch test unexpectedly succeeded.\n' >&2
  exit 1
fi
mv "$TMP/systemd/hermesui-launcher.service.saved" "$TMP/systemd/hermesui-launcher.service"
if HERMESUI_PORT=18994 "$ROOT/hermesui/installer/tailnet-status.sh" >"$TMP/status-env-port.out" 2>"$TMP/status-env-port.err"; then
  printf 'Status environment/state port mismatch test unexpectedly succeeded.\n' >&2
  exit 1
fi

# Status must preserve route provenance and reject Foreground or mixed handlers.
for mode in foreground_owned mixed_owned mixed_foreign wrong_listener; do
  export HERMESUI_QA_SERVE_MODE="$mode"
  if "$ROOT/hermesui/installer/tailnet-status.sh" >"$TMP/status-${mode}.out" 2>"$TMP/status-${mode}.err"; then
    printf '%s status provenance test unexpectedly succeeded.\n' "$mode" >&2
    exit 1
  fi
  grep -Eq 'Foreground or mixed Serve handler|not routed to this HermesUI service' "$TMP/status-${mode}.err"
done
export HERMESUI_QA_SERVE_MODE=owned
systemd-analyze --user verify "$TMP/systemd/hermesui-launcher.service"

python3 - "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env" "$LOG" "$TMP/setup.out" "$TMP/status.out" "$TMP/port.err" "$TMP/unit.err" "$TMP/missing-state.err" "$TMP/route.err" "$TMP/foreground-route.err" "$TMP/setup-manual_owned.err" "$TMP/setup-foreground_owned.err" "$TMP/setup-mixed_owned.err" "$TMP/funnel.err" <<'PY'
import os
from pathlib import Path
import sys
unit_path = Path(sys.argv[1])
enable_link = Path(sys.argv[2])
runtime_home = unit_path.parents[1] / 'home' / '.hermes'
unit = unit_path.read_text(encoding='utf-8')
state, log, setup, status, port_err, unit_err, missing_state_err, route_err, foreground_route_err, manual_route_err, foreground_owned_err, mixed_owned_err, funnel_err = [Path(value).read_text(encoding='utf-8') for value in sys.argv[3:]]
assert enable_link.is_symlink()
assert os.readlink(enable_link) == str(unit_path)
assert '# Managed by HermesUI Tailnet installer' in unit
assert 'WorkingDirectory="' not in unit
assert 'HERMES_WEBUI_HOST=127.0.0.1' in unit
assert 'HERMES_WEBUI_PORT=18993' in unit
assert 'HERMES_WEBUI_PRESERVE_ENV=1' in unit
assert 'HERMES_WEBUI_SECURE=1' in unit
assert 'HERMES_WEBUI_COOKIE_NAME=hermesui_session' in unit
assert 'HERMES_WEBUI_PROFILE_COOKIE_NAME=hermesui_profile' in unit
assert 'HERMESUI_MODE=standalone' in unit
assert 'HERMESUI_PROFILE=default' in unit
assert f'HERMES_HOME={runtime_home}' in unit
assert 'HERMES_WEBUI_COOKIE_PATH' not in unit
assert 'systemd-start-owned.py' in unit
assert '--unit hermesui.service' in unit
assert '--port 18993' in unit
assert state == (
    'HERMESUI_STATE_VERSION=2\n'
    'HERMESUI_MODE=standalone\n'
    f'HERMESUI_HERMES_HOME={runtime_home}\n'
    'HERMESUI_PROFILE=default\n'
    'HERMESUI_PORT=18993\n'
    'HERMESUI_TCP_443_CREATED=1\n'
)
assert 'tailscale serve --bg --https=443 --set-path=/hermesUI http://127.0.0.1:18993' in log
assert 'https://device.tailnet.example.ts.net/hermesUI/' in log
assert log.count('start-owned-service ') == 3
assert f'--hermes-home {runtime_home} --profile default --port 18993' in log
assert 'HermesUI is ready.' in setup
assert 'URL: https://device.tailnet.example.ts.net/hermesUI/' in setup
assert 'HermesUI URL: https://device.tailnet.example.ts.net/hermesUI/' in status
assert 'Mode: standalone' in status
assert f'Hermes home: {runtime_home}' in status
assert 'Profile: default' in status
assert 'already in use' in port_err
assert 'not managed by HermesUI' in unit_err
assert 'install.env is missing' in missing_state_err
assert 'already belongs to a different handler' in route_err
assert 'already belongs to a different handler' in foreground_route_err
assert 'may be a manual route' in manual_route_err
assert 'Foreground or mixed handler' in foreground_owned_err
assert 'Foreground or mixed handler' in mixed_owned_err
assert 'Tailscale Funnel is enabled' in funnel_err
PY

# A failed managed rerun must restore the previous unit, state, route, and
# running service exactly rather than deleting a healthy prior installation.
cp -p "$TMP/systemd/hermesui-launcher.service" "$TMP/systemd/hermesui-launcher.service.before-failed-rerun"
cp -p "$TMP/state/install.env" "$TMP/state/install.env.before-failed-rerun"
before_serve_count="$(grep -c 'tailscale serve --bg --https=443 --set-path=/hermesUI' "$LOG" || true)"
export HERMESUI_QA_SERVE_MODE=owned HERMESUI_QA_ACTIVE=1 HERMESUI_QA_TAILNET_HEALTH_FAIL=1
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/rerun-late-health.out" 2>"$TMP/rerun-late-health.err"; then
  printf 'Failed managed rerun rollback test unexpectedly succeeded.\n' >&2
  exit 1
fi
after_serve_count="$(grep -c 'tailscale serve --bg --https=443 --set-path=/hermesUI' "$LOG" || true)"
[[ "$after_serve_count" -eq $((before_serve_count + 2)) ]]
cmp -s "$TMP/systemd/hermesui-launcher.service.before-failed-rerun" "$TMP/systemd/hermesui-launcher.service"
cmp -s "$TMP/state/install.env.before-failed-rerun" "$TMP/state/install.env"
[[ -e "$ROUTE_STATE" && -e "$SERVICE_STATE" ]]
grep -q 'failed setup changes were rolled back' "$TMP/rerun-late-health.err"
unset HERMESUI_QA_TAILNET_HEALTH_FAIL
rm -f "$TMP/systemd/hermesui-launcher.service.before-failed-rerun" "$TMP/state/install.env.before-failed-rerun"

# A stop-time systemd query error after candidate activation must preserve the
# runtime ownership files and must never claim complete rollback.
export HERMESUI_QA_STOP_QUERY_FAIL_FLAG="$TMP/stop-query-fail"
export HERMESUI_QA_TAILNET_HEALTH_FAIL=1
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/rerun-stop-query.out" 2>"$TMP/rerun-stop-query.err"; then
  printf 'Stop-time runtime-state query failure unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ -e "$SERVICE_STATE" && -e "$TMP/systemd/hermesui-launcher.service" && -L "$ENABLE_LINK" && -e "$TMP/state/install.env" ]]
grep -q 'could not be queried or stopped authoritatively' "$TMP/rerun-stop-query.err"
grep -q 'automatic rollback was incomplete' "$TMP/rerun-stop-query.err"
grep -q 'rollback evidence was preserved' "$TMP/rerun-stop-query.err"
if grep -q 'failed setup changes were rolled back' "$TMP/rerun-stop-query.err"; then
  printf 'Stop-time query failure falsely claimed complete rollback.\n' >&2
  exit 1
fi
unset HERMESUI_QA_TAILNET_HEALTH_FAIL HERMESUI_QA_STOP_QUERY_FAIL_FLAG
rm -f "$TMP/stop-query-fail"
rm -rf "$TMP/state"/.install.env.txn.*
rm -f "$TMP/state"/.install.env.rollback.* "$TMP/systemd"/.hermesui.service.rollback.*
"$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/rerun-after-stop-query.out"

# If Funnel appears after an owned route is applied, rollback must never restore
# a non-absent route. It removes the still-owned candidate while restoring the
# prior local unit, state, and service bytes, but must report that route recovery
# remains incomplete and preserve recovery evidence.
cp -p "$TMP/systemd/hermesui-launcher.service" "$TMP/systemd/hermesui-launcher.service.before-funnel-rollback"
cp -p "$TMP/state/install.env" "$TMP/state/install.env.before-funnel-rollback"
export HERMESUI_QA_ROLLBACK_FUNNEL_FLAG="$TMP/rollback-funnel"
export HERMESUI_QA_TAILNET_HEALTH_FAIL=1
before_funnel_off_count="$(grep -c 'set-path=/hermesUI off' "$LOG" || true)"
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/rerun-funnel-rollback.out" 2>"$TMP/rerun-funnel-rollback.err"; then
  printf 'Funnel-safe rerun rollback test unexpectedly succeeded.\n' >&2
  exit 1
fi
after_funnel_off_count="$(grep -c 'set-path=/hermesUI off' "$LOG" || true)"
[[ "$after_funnel_off_count" -eq $((before_funnel_off_count + 1)) ]]
cmp -s "$TMP/systemd/hermesui-launcher.service.before-funnel-rollback" "$TMP/systemd/hermesui-launcher.service"
cmp -s "$TMP/state/install.env.before-funnel-rollback" "$TMP/state/install.env"
[[ ! -e "$ROUTE_STATE" && -e "$SERVICE_STATE" ]]
grep -q 'automatic rollback was incomplete' "$TMP/rerun-funnel-rollback.err"
grep -q 'Disable Funnel and rerun setup' "$TMP/rerun-funnel-rollback.err"
if grep -q 'failed setup changes were rolled back' "$TMP/rerun-funnel-rollback.err"; then
  printf 'Funnel-safe rerun falsely claimed complete rollback.\n' >&2
  exit 1
fi
grep -q 'rollback evidence was preserved' "$TMP/rerun-funnel-rollback.err"
unset HERMESUI_QA_TAILNET_HEALTH_FAIL HERMESUI_QA_ROLLBACK_FUNNEL_FLAG
rm -f "$TMP/rollback-funnel" "$TMP/systemd/hermesui-launcher.service.before-funnel-rollback" "$TMP/state/install.env.before-funnel-rollback"
rm -rf "$TMP/state"/.install.env.txn.*
rm -f "$TMP/state"/.install.env.rollback.* "$TMP/systemd"/.hermesui.service.rollback.*
: >"$ROUTE_STATE"

# Rollback sources must remain on each managed destination filesystem even when
# TMPDIR is a different device. A late failure must restore exact bytes and modes.
if [[ -d /dev/shm && "$(stat -c %d /dev/shm)" != "$(stat -c %d "$TMP")" ]]; then
  CROSS_TMP="$(mktemp -d /dev/shm/hermesui-crossfs.XXXXXX)"
  cp -p "$TMP/systemd/hermesui-launcher.service" "$TMP/systemd/hermesui-launcher.service.before-crossfs"
  cp -p "$TMP/state/install.env" "$TMP/state/install.env.before-crossfs"
  unit_mode_before="$(stat -c %a "$TMP/systemd/hermesui-launcher.service")"
  state_mode_before="$(stat -c %a "$TMP/state/install.env")"
  link_target_before="$(readlink "$ENABLE_LINK")"
  export HERMESUI_QA_TAILNET_HEALTH_FAIL=1
  if TMPDIR="$CROSS_TMP" "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/crossfs-rerun.out" 2>"$TMP/crossfs-rerun.err"; then
    printf 'Cross-filesystem rollback test unexpectedly succeeded.\n' >&2
    exit 1
  fi
  unset HERMESUI_QA_TAILNET_HEALTH_FAIL
  cmp -s "$TMP/systemd/hermesui-launcher.service.before-crossfs" "$TMP/systemd/hermesui-launcher.service"
  cmp -s "$TMP/state/install.env.before-crossfs" "$TMP/state/install.env"
  [[ "$(stat -c %a "$TMP/systemd/hermesui-launcher.service")" == "$unit_mode_before" ]]
  [[ "$(stat -c %a "$TMP/state/install.env")" == "$state_mode_before" ]]
  [[ -L "$ENABLE_LINK" && "$(readlink "$ENABLE_LINK")" == "$link_target_before" ]]
  [[ -e "$SERVICE_STATE" && -e "$ROUTE_STATE" ]]
  if compgen -G "$TMP/state/.install.env.rollback.*" >/dev/null || compgen -G "$TMP/systemd/.hermesui.service.rollback.*" >/dev/null; then
    printf 'Cross-filesystem rollback left destination-adjacent rollback files after success.\n' >&2
    exit 1
  fi
  grep -q 'failed setup changes were rolled back' "$TMP/crossfs-rerun.err"
  rm -f "$TMP/systemd/hermesui-launcher.service.before-crossfs" "$TMP/state/install.env.before-crossfs"
  rm -rf "$CROSS_TMP"
  CROSS_TMP=""
fi

"$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/uninstall.out"
[[ ! -e "$TMP/systemd/hermesui-launcher.service" ]]
[[ ! -e "$TMP/state/install.env" ]]
python3 - "$LOG" "$TMP/uninstall.out" <<'PY'
from pathlib import Path
import sys
log, output = [Path(value).read_text(encoding='utf-8') for value in sys.argv[1:]]
assert 'tailscale serve --https=443 --set-path=/hermesUI off' in log
assert 'stop-owned-process --pid 424242' in log
assert 'systemctl --user disable' not in log
assert 'Tailnet route: removed' in output
PY

# A same-path handler on another HTTPS listener is never adopted as the
# canonical route; setup creates hostname:443, status requires it, and
# uninstall removes only hostname:443 while leaving the other listener alone.
rm -f "$ROUTE_STATE"
export HERMESUI_PORT=18993 HERMESUI_QA_SERVE_MODE=wrong_then_owned HERMESUI_QA_ACTIVE=0
"$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/wrong-listener-setup.out"
unset HERMESUI_PORT
export HERMESUI_QA_ACTIVE=1
"$ROOT/hermesui/installer/tailnet-status.sh" >"$TMP/wrong-listener-status.out"
"$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/wrong-listener-uninstall.out"
[[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$TMP/state/install.env" && ! -e "$ROUTE_STATE" ]]

# A late canonical Tailnet health failure must roll back every fresh-install
# mutation instead of leaving a unit, state file, active service, or route.
rm -f "$ROUTE_STATE" "$SERVICE_STATE" "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env"
export HERMESUI_PORT=18993 HERMESUI_QA_SERVE_MODE=missing HERMESUI_QA_ACTIVE=0 HERMESUI_QA_TAILNET_HEALTH_FAIL=1
before_off_count="$(grep -c 'set-path=/hermesUI off' "$LOG" || true)"
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/late-health.out" 2>"$TMP/late-health.err"; then
  printf 'Late Tailnet health failure test unexpectedly succeeded.\n' >&2
  exit 1
fi
after_off_count="$(grep -c 'set-path=/hermesUI off' "$LOG" || true)"
[[ "$after_off_count" -eq $((before_off_count + 1)) ]]
[[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$TMP/state/install.env" && ! -e "$ROUTE_STATE" && ! -e "$SERVICE_STATE" ]]
grep -q 'failed setup changes were rolled back' "$TMP/late-health.err"
unset HERMESUI_QA_TAILNET_HEALTH_FAIL

# A route reassigned after setup mutation must be preserved rather than
# removed by compensation based on stale ownership data.
rm -f "$ROUTE_STATE" "$ROUTE_FOREIGN_STATE" "$SERVICE_STATE" "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env"
export HERMESUI_PORT=18993 HERMESUI_QA_SERVE_MODE=missing HERMESUI_QA_ACTIVE=0 HERMESUI_QA_TAILNET_HEALTH_FAIL=1 HERMESUI_QA_ROLLBACK_RACE=route
before_off_count="$(grep -c 'set-path=/hermesUI off' "$LOG" || true)"
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/route-race.out" 2>"$TMP/route-race.err"; then
  printf 'Route rollback race test unexpectedly succeeded.\n' >&2
  exit 1
fi
after_off_count="$(grep -c 'set-path=/hermesUI off' "$LOG" || true)"
[[ "$after_off_count" == "$before_off_count" && -e "$ROUTE_FOREIGN_STATE" ]]
[[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$TMP/state/install.env" && ! -e "$SERVICE_STATE" ]]
grep -q 'Serve route changed ownership during setup; it was preserved' "$TMP/route-race.err"
grep -q 'automatic rollback was incomplete' "$TMP/route-race.err"
if grep -q 'failed setup changes were rolled back' "$TMP/route-race.err"; then
  printf 'Route ownership race was incorrectly reported as a complete rollback.\n' >&2
  exit 1
fi

# A launcher replaced after setup mutation must be preserved, while rollback
# stops only the exact managed runtime that setup started.
rm -f "$ROUTE_STATE" "$ROUTE_FOREIGN_STATE" "$SERVICE_STATE" "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env"
export HERMESUI_QA_ROLLBACK_RACE=unit
before_stop_count="$(grep -c 'stop-owned-process --pid' "$LOG" || true)"
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/unit-race.out" 2>"$TMP/unit-race.err"; then
  printf 'Unit rollback race test unexpectedly succeeded.\n' >&2
  exit 1
fi
after_stop_count="$(grep -c 'stop-owned-process --pid' "$LOG" || true)"
[[ "$after_stop_count" -eq $((before_stop_count + 2)) && ! -e "$SERVICE_STATE" ]]
grep -q 'Description=Foreign takeover' "$TMP/systemd/hermesui-launcher.service"
[[ ! -e "$TMP/state/install.env" && ! -e "$ROUTE_STATE" ]]
grep -q 'launcher changed ownership during setup; the foreign launcher was preserved' "$TMP/unit-race.err"
grep -q 'automatic rollback was incomplete' "$TMP/unit-race.err"

# A replaced install.env must likewise be preserved.
rm -f "$ROUTE_STATE" "$ROUTE_FOREIGN_STATE" "$SERVICE_STATE" "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env"
export HERMESUI_QA_ROLLBACK_RACE=state
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/state-race.out" 2>"$TMP/state-race.err"; then
  printf 'State rollback race test unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q '^FOREIGN_STATE=1$' "$TMP/state/install.env"
[[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$ROUTE_STATE" && ! -e "$SERVICE_STATE" ]]
grep -q 'install.env changed ownership during setup; it was preserved' "$TMP/state-race.err"
grep -q 'automatic rollback was incomplete' "$TMP/state-race.err"
unset HERMESUI_QA_TAILNET_HEALTH_FAIL HERMESUI_QA_ROLLBACK_RACE
rm -f "$ROUTE_FOREIGN_STATE" "$TMP/state/install.env"

# A manually configured exact route must never be adopted without install state.
rm -f "$ROUTE_STATE" "$TMP/state/install.env" "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK"
export HERMESUI_PORT=18993 HERMESUI_QA_SERVE_MODE=manual_owned HERMESUI_QA_ACTIVE=0
before_count="$(python3 - "$LOG" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).read_text().count('set-path=/hermesUI off'))
PY
)"
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/manual-route.out" 2>"$TMP/manual-route.err"; then
  printf 'Manual route ownership test unexpectedly succeeded.\n' >&2
  exit 1
fi
after_count="$(python3 - "$LOG" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).read_text().count('set-path=/hermesUI off'))
PY
)"
[[ "$before_count" == "$after_count" ]]
python3 - "$TMP/manual-route.err" <<'PY'
from pathlib import Path
import sys
assert 'may be a manual route, so nothing was changed' in Path(sys.argv[1]).read_text()
PY

# Uninstall preserves a route reassigned to another app.
mkdir -p "$TMP/state" "$TMP/systemd"
printf 'HERMESUI_PORT=18993\nHERMESUI_TCP_443_CREATED=1\n' >"$TMP/state/install.env"
"$ROOT/hermesui/installer/systemd-launcher-unit.py" write "$TMP/systemd/hermesui-launcher.service" \
  --repo-root "$ROOT" --home "$TMP/home" --host 127.0.0.1 --port 18993 --legacy
rm -f "$ROUTE_STATE"
export HERMESUI_QA_SERVE_MODE=foreign HERMESUI_QA_ACTIVE=1
before_count="$(python3 - "$LOG" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).read_text().count('set-path=/hermesUI off'))
PY
)"
"$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/foreign-uninstall.out" 2>"$TMP/foreign-uninstall.err"
after_count="$(python3 - "$LOG" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).read_text().count('set-path=/hermesUI off'))
PY
)"
[[ "$before_count" == "$after_count" ]]
python3 - "$TMP/foreign-uninstall.err" <<'PY'
from pathlib import Path
import sys
assert 'points to another handler, so it was preserved' in Path(sys.argv[1]).read_text()
PY

prepare_owned_install() {
  mkdir -p "$TMP/state" "$TMP/systemd/default.target.wants"
  printf 'HERMESUI_PORT=18993\nHERMESUI_TCP_443_CREATED=1\n' >"$TMP/state/install.env"
  "$ROOT/hermesui/installer/systemd-launcher-unit.py" write "$TMP/systemd/hermesui-launcher.service" \
    --repo-root "$ROOT" --home "$TMP/home" --host 127.0.0.1 --port 18993 --legacy
  rm -f "$ENABLE_LINK"
  rm -f "$STOPPED_STATE"
  ln -s "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK"
}

# Present-null Serve ownership state is not absence. Uninstall must fail before
# stopping the service or discarding the unit, enable link, and install state.
for null_mode in listener_null handler_null; do
  prepare_owned_install
  : >"$SERVICE_STATE"
  : >"$ROUTE_STATE"
  : >"$LOG"
  export HERMESUI_QA_SERVE_MODE="$null_mode" HERMESUI_QA_ACTIVE=1
  if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/${null_mode}-uninstall.out" 2>"$TMP/${null_mode}-uninstall.err"; then
    printf 'Uninstall accepted ownership-ambiguous Serve state: %s.\n' "$null_mode" >&2
    exit 1
  fi
  [[ -e "$TMP/systemd/hermesui-launcher.service" && -L "$ENABLE_LINK" && -e "$TMP/state/install.env" && -e "$SERVICE_STATE" && -e "$ROUTE_STATE" ]]
  if grep -qE 'stop-owned-process|set-path=/hermesUI off' "$LOG"; then
    printf 'Uninstall mutated state for ownership-ambiguous Serve mode: %s.\n' "$null_mode" >&2
    exit 1
  fi
  grep -q 'Serve ownership could not be verified, so nothing was changed' "$TMP/${null_mode}-uninstall.err"
  rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env" "$SERVICE_STATE" "$ROUTE_STATE"
done

# A failed authoritative systemd provenance lookup must retain its distinctive
# status and perform no process stop, route, unit, link, or state mutation.
prepare_owned_install
: >"$ROUTE_STATE"
: >"$SERVICE_STATE"
: >"$LOG"
export HERMESUI_QA_SERVE_MODE=owned HERMESUI_QA_ACTIVE=1 HERMESUI_QA_SYSTEMCTL_FAIL=show
set +e
"$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/show-fail.out" 2>"$TMP/show-fail.err"
show_status=$?
set -e
[[ "$show_status" == "76" ]]
[[ -e "$TMP/systemd/hermesui-launcher.service" && -e "$TMP/state/install.env" && -e "$ROUTE_STATE" && -e "$SERVICE_STATE" ]]
if grep -q 'stop-owned-process' "$LOG"; then
  printf 'Uninstall ownership gate unexpectedly stopped the service.\n' >&2
  exit 1
fi
if grep -q 'set-path=/hermesUI off' "$LOG"; then
  printf 'Uninstall ownership gate unexpectedly removed the route.\n' >&2
  exit 1
fi
grep -q 'Could not verify the systemd provenance' "$TMP/show-fail.err"
unset HERMESUI_QA_SYSTEMCTL_FAIL
rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env" "$ROUTE_STATE" "$SERVICE_STATE"

# An ActiveState lookup error must fail before process, route, unit, link, or
# install-state mutation instead of being treated as an inactive service.
prepare_owned_install
: >"$ROUTE_STATE"
: >"$SERVICE_STATE"
: >"$LOG"
export HERMESUI_QA_SERVE_MODE=owned HERMESUI_QA_ACTIVE=1 HERMESUI_QA_SYSTEMCTL_FAIL=active-state
set +e
"$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/active-state-fail.out" 2>"$TMP/active-state-fail.err"
active_state_status=$?
set -e
[[ "$active_state_status" == "78" ]]
[[ -e "$TMP/systemd/hermesui-launcher.service" && -e "$TMP/state/install.env" && -e "$ROUTE_STATE" && -e "$SERVICE_STATE" && -L "$ENABLE_LINK" ]]
if grep -qE 'stop-owned-process|set-path=/hermesUI off' "$LOG"; then
  printf 'Uninstall ActiveState failure gate unexpectedly mutated runtime state.\n' >&2
  exit 1
fi
grep -q 'Could not verify the exact hermesui.service ActiveState, LoadState, and MainPID' "$TMP/active-state-fail.err"
unset HERMESUI_QA_SYSTEMCTL_FAIL
rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env" "$ROUTE_STATE" "$SERVICE_STATE"

# Replacing the owned unit during the later route-status read must be detected
# before process stop or removal, and the byte-distinct replacement must survive.
prepare_owned_install
: >"$ROUTE_STATE"
: >"$SERVICE_STATE"
: >"$LOG"
rm -f "$HERMESUI_QA_UNIT_RACE_DONE"
export HERMESUI_QA_UNINSTALL_UNIT_RACE=1
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/uninstall-unit-race.out" 2>"$TMP/uninstall-unit-race.err"; then
  printf 'Uninstall unit takeover test unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q 'Description=Foreign takeover before disable' "$TMP/systemd/hermesui-launcher.service"
[[ -e "$TMP/state/install.env" && -e "$ROUTE_STATE" && -e "$SERVICE_STATE" ]]
if grep -q 'stop-owned-process' "$LOG"; then
  printf 'Uninstall ownership gate unexpectedly stopped the service.\n' >&2
  exit 1
fi
grep -q 'changed ownership after preflight' "$TMP/uninstall-unit-race.err"
unset HERMESUI_QA_UNINSTALL_UNIT_RACE
rm -f "$HERMESUI_QA_UNIT_RACE_DONE" "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env" "$ROUTE_STATE" "$SERVICE_STATE"

# A replacement installed after the exact owned process stops must be revalidated and
# preserved rather than removed from the fixed unit path.
prepare_owned_install
: >"$SERVICE_STATE"
: >"$LOG"
rm -f "$ROUTE_STATE"
export HERMESUI_QA_SERVE_MODE=missing HERMESUI_QA_UNINSTALL_UNIT_STOP_RACE=1
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/uninstall-unit-stop-race.out" 2>"$TMP/uninstall-unit-stop-race.err"; then
  printf 'Uninstall post-stop unit takeover test unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q 'Description=Foreign takeover after owned process stop' "$TMP/systemd/hermesui-launcher.service"
[[ -e "$TMP/state/install.env" ]]
grep -q 'changed ownership while the loaded HermesUI service was stopping' "$TMP/uninstall-unit-stop-race.err"
unset HERMESUI_QA_UNINSTALL_UNIT_STOP_RACE
rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env" "$SERVICE_STATE"

# A same-name foreign takeover at the process-stop helper boundary must not be
# signaled, disabled, or detached from its enable link.
prepare_owned_install
: >"$SERVICE_STATE"
: >"$LOG"
rm -f "$ROUTE_STATE" "$HERMESUI_QA_FOREIGN_ACTIVE"
export HERMESUI_QA_SERVE_MODE=missing HERMESUI_QA_PROCESS_ENTRY_TAKEOVER=1
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/uninstall-process-entry.out" 2>"$TMP/uninstall-process-entry.err"; then
  printf 'Process-stop command-entry takeover test unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q 'Description=Foreign takeover at process-stop entry' "$TMP/systemd/hermesui-launcher.service"
[[ -L "$ENABLE_LINK" && "$(readlink "$ENABLE_LINK")" == "$TMP/systemd/hermesui-launcher.service" ]]
[[ -e "$TMP/state/install.env" && -e "$SERVICE_STATE" && -e "$HERMESUI_QA_FOREIGN_ACTIVE" ]]
if grep -q 'systemctl --user disable\|systemctl --user stop' "$LOG"; then
  printf 'Process-stop boundary used a name-based destructive systemd command.\n' >&2
  exit 1
fi
grep -q 'Could not stop hermesui.service' "$TMP/uninstall-process-entry.err"
unset HERMESUI_QA_PROCESS_ENTRY_TAKEOVER
rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env" "$SERVICE_STATE" "$HERMESUI_QA_FOREIGN_ACTIVE"

# A route reassigned during service cleanup must be re-read immediately before
# route-off. The foreign route and retry state must survive with no off call.
prepare_owned_install
: >"$ROUTE_STATE"
: >"$SERVICE_STATE"
: >"$LOG"
rm -f "$ROUTE_FOREIGN_STATE"
export HERMESUI_QA_SERVE_MODE=owned HERMESUI_QA_UNINSTALL_ROUTE_RACE=1
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/uninstall-route-race.out" 2>"$TMP/uninstall-route-race.err"; then
  printf 'Uninstall route takeover test unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ -e "$ROUTE_FOREIGN_STATE" && -e "$TMP/state/install.env" && ! -e "$TMP/systemd/hermesui-launcher.service" ]]
if grep -q 'set-path=/hermesUI off' "$LOG"; then
  printf 'Uninstall ownership gate unexpectedly removed the route.\n' >&2
  exit 1
fi
grep -q 'changed ownership before route cleanup' "$TMP/uninstall-route-race.err"
unset HERMESUI_QA_UNINSTALL_ROUTE_RACE
rm -f "$ROUTE_FOREIGN_STATE" "$TMP/state/install.env" "$SERVICE_STATE"

# State ownership is part of route authority. Replacing install.env during
# service cleanup must preserve both the foreign state and the route.
prepare_owned_install
: >"$ROUTE_STATE"
: >"$SERVICE_STATE"
: >"$LOG"
export HERMESUI_QA_SERVE_MODE=owned HERMESUI_QA_UNINSTALL_STATE_RACE=1
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/uninstall-state-race.out" 2>"$TMP/uninstall-state-race.err"; then
  printf 'Uninstall state takeover test unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q '^FOREIGN_STATE=1$' "$TMP/state/install.env"
[[ -e "$ROUTE_STATE" && ! -e "$TMP/systemd/hermesui-launcher.service" ]]
if grep -q 'set-path=/hermesUI off' "$LOG"; then
  printf 'Uninstall ownership gate unexpectedly removed the route.\n' >&2
  exit 1
fi
grep -q 'install.env changed ownership before route cleanup' "$TMP/uninstall-state-race.err"
unset HERMESUI_QA_UNINSTALL_STATE_RACE
rm -f "$TMP/state/install.env" "$ROUTE_STATE" "$SERVICE_STATE"

# Exact command-entry boundary: a foreign state file appearing as fresh state
# publication begins must survive byte-identically and must never be adopted.
rm -f "$TMP/state/install.env" "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$ROUTE_STATE" "$ROUTE_FOREIGN_STATE" "$SERVICE_STATE"
export HERMESUI_PORT=18993 HERMESUI_QA_SERVE_MODE=missing HERMESUI_QA_ACTIVE=0 HERMESUI_QA_PATH_RACE=setup_state
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/setup-state-boundary.out" 2>"$TMP/setup-state-boundary.err"; then
  printf 'Setup state publication boundary test unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q '^FOREIGN_STATE=1$' "$TMP/state/install.env"
[[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$ROUTE_STATE" && ! -e "$SERVICE_STATE" ]]
grep -q 'install.env appeared before publication' "$TMP/setup-state-boundary.err"
unset HERMESUI_QA_PATH_RACE
rm -f "$TMP/state/install.env"

# Exact command-entry boundary: a foreign unit appearing as fresh unit
# publication begins must survive while the transaction removes its own state.
export HERMESUI_QA_PATH_RACE=setup_unit
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/setup-unit-boundary.out" 2>"$TMP/setup-unit-boundary.err"; then
  printf 'Setup unit publication boundary test unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q 'Description=Foreign setup takeover' "$TMP/systemd/hermesui-launcher.service"
[[ ! -e "$TMP/state/install.env" && ! -e "$ROUTE_STATE" && ! -e "$SERVICE_STATE" ]]
grep -q 'systemd unit appeared before publication' "$TMP/setup-unit-boundary.err"
unset HERMESUI_QA_PATH_RACE
rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK"

# A unit takeover after daemon reload must be detected before enable-link publication.
rm -f "$TMP/state/install.env" "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$ROUTE_STATE" "$SERVICE_STATE"
: >"$LOG"
export HERMESUI_QA_SETUP_UNIT_RACE=after_daemon_reload
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/setup-after-reload.out" 2>"$TMP/setup-after-reload.err"; then
  printf 'Post-daemon-reload takeover test unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q 'Description=Foreign takeover after daemon reload' "$TMP/systemd/hermesui-launcher.service"
[[ ! -e "$TMP/state/install.env" && ! -L "$ENABLE_LINK" && ! -e "$ROUTE_STATE" && ! -e "$SERVICE_STATE" ]]
if grep -q 'start-owned-service ' "$LOG"; then
  printf 'Post-daemon-reload takeover reached service start.\n' >&2
  exit 1
fi
grep -q 'changed ownership after daemon reload' "$TMP/setup-after-reload.err"
unset HERMESUI_QA_SETUP_UNIT_RACE
rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK"

# A foreign enable path appearing at the atomic link-publication boundary must
# survive, and setup must not reach the transient service start operation.
: >"$LOG"
export HERMESUI_QA_PATH_RACE=setup_enable_link
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/setup-enable-link-boundary.out" 2>"$TMP/setup-enable-link-boundary.err"; then
  printf 'Enable-link publication boundary test unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ -L "$ENABLE_LINK" ]]
[[ "$(readlink "$ENABLE_LINK")" == "/foreign/unit" ]]
[[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$TMP/state/install.env" && ! -e "$ROUTE_STATE" && ! -e "$SERVICE_STATE" ]]
if grep -q 'start-owned-service ' "$LOG"; then
  printf 'Enable-link publication boundary reached service start.\n' >&2
  exit 1
fi
grep -q 'systemd unit or enable link changed ownership before publication' "$TMP/setup-enable-link-boundary.err"
unset HERMESUI_QA_PATH_RACE
rm -f "$ENABLE_LINK"

# Replacing the launcher as enable-link creation enters must be rejected before
# the foreign replacement acquires any enable link.
rm -f "$TMP/state/install.env" "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$ROUTE_STATE" "$SERVICE_STATE" "$STOPPED_STATE" "$HERMESUI_QA_FOREIGN_ACTIVE"
export HERMESUI_PORT=18993 HERMESUI_QA_SERVE_MODE=missing HERMESUI_QA_ACTIVE=0 HERMESUI_QA_PATH_RACE=setup_enable_unit_takeover
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/setup-enable-unit-entry.out" 2>"$TMP/setup-enable-unit-entry.err"; then
  printf 'Setup enable-target takeover test unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q 'Description=Foreign unit at link-create entry' "$TMP/systemd/hermesui-launcher.service"
[[ ! -L "$ENABLE_LINK" && ! -e "$TMP/state/install.env" && ! -e "$ROUTE_STATE" && ! -e "$SERVICE_STATE" ]]
grep -q 'systemd unit or enable link changed ownership before publication' "$TMP/setup-enable-unit-entry.err"
unset HERMESUI_QA_PATH_RACE
rm -f "$TMP/systemd/hermesui-launcher.service"

# Replacing the persistent launcher at the transient-service command boundary
# cannot redirect the exact inline runtime contract. Setup detects the launcher
# takeover, stops only its verified runtime, and preserves the foreign launcher.
: >"$LOG"
export HERMESUI_QA_SETUP_UNIT_RACE=service_start_entry
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/setup-start-entry.out" 2>"$TMP/setup-start-entry.err"; then
  printf 'Service-start entry takeover test unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q 'Description=Foreign takeover at transient service start' "$TMP/systemd/hermesui-launcher.service"
[[ ! -e "$TMP/state/install.env" && ! -e "$ROUTE_STATE" && ! -e "$SERVICE_STATE" && ! -e "$HERMESUI_QA_FOREIGN_ACTIVE" ]]
grep -q 'start-owned-service ' "$LOG"
grep -q 'stop-owned-process --pid' "$LOG"
if grep -q 'systemctl --user restart\|systemctl --user start\|systemctl --user stop' "$LOG"; then
  printf 'Service-start boundary used a name-based destructive systemd command.\n' >&2
  exit 1
fi
grep -q 'changed ownership during service start' "$TMP/setup-start-entry.err"
unset HERMESUI_QA_SETUP_UNIT_RACE
rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$SERVICE_STATE"

# A same-name transient runtime collision fails atomically. The foreign runtime
# is not signaled and installer-owned state is rolled back.
: >"$LOG"
export HERMESUI_QA_RUNTIME_COLLISION=1
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/runtime-collision.out" 2>"$TMP/runtime-collision.err"; then
  printf 'Transient runtime collision test unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ -e "$HERMESUI_QA_FOREIGN_ACTIVE" && ! -e "$TMP/state/install.env" && ! -e "$ROUTE_STATE" && ! -e "$SERVICE_STATE" && ! -e "$TMP/systemd/hermesui-launcher.service" ]]
if grep -q 'systemctl --user restart\|systemctl --user start\|systemctl --user stop' "$LOG"; then
  printf 'Runtime collision used a name-based destructive systemd command.\n' >&2
  exit 1
fi
unset HERMESUI_QA_RUNTIME_COLLISION
rm -f "$HERMESUI_QA_FOREIGN_ACTIVE"

# Exact provider mutation boundary: a foreign route appearing inside the CAS
# helper must be preserved, and local setup resources must roll back.
export HERMESUI_QA_CAS_ROUTE_RACE=1
set +e
"$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/setup-route-cas-boundary.out" 2>"$TMP/setup-route-cas-boundary.err"
setup_route_status=$?
set -e
[[ "$setup_route_status" == "75" ]]
[[ -e "$ROUTE_FOREIGN_STATE" && ! -e "$ROUTE_STATE" && ! -e "$TMP/state/install.env" && ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$SERVICE_STATE" ]]
grep -q 'Serve route changed ownership during setup; it was preserved' "$TMP/setup-route-cas-boundary.err"
unset HERMESUI_QA_CAS_ROUTE_RACE
rm -f "$ROUTE_FOREIGN_STATE"

# Exact destructive boundary: replacing the unit as atomic removal begins must
# preserve the replacement and retry state instead of deleting foreign bytes.
prepare_owned_install
: >"$SERVICE_STATE"
export HERMESUI_QA_SERVE_MODE=missing HERMESUI_QA_ACTIVE=1 HERMESUI_QA_PATH_RACE=uninstall_unit_rm
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/uninstall-unit-remove-boundary.out" 2>"$TMP/uninstall-unit-remove-boundary.err"; then
  printf 'Uninstall unit removal boundary test unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q 'Description=Foreign removal takeover' "$TMP/systemd/hermesui-launcher.service"
[[ -e "$TMP/state/install.env" ]]
grep -q 'unit file could not be removed' "$TMP/uninstall-unit-remove-boundary.err"
unset HERMESUI_QA_PATH_RACE
rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env" "$SERVICE_STATE"

# A foreign symlink replacing the enable link at its atomic removal boundary
# must survive, while the managed unit, state, and active service are restored.
prepare_owned_install
: >"$SERVICE_STATE"
: >"$LOG"
export HERMESUI_QA_PATH_RACE=uninstall_enable_link
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/uninstall-enable-link-boundary.out" 2>"$TMP/uninstall-enable-link-boundary.err"; then
  printf 'Uninstall enable-link boundary test unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ -L "$ENABLE_LINK" && "$(readlink "$ENABLE_LINK")" == "/foreign/unit" ]]
[[ -e "$TMP/systemd/hermesui-launcher.service" && -e "$TMP/state/install.env" && -e "$SERVICE_STATE" ]]
grep -q 'enable link changed ownership and was preserved' "$TMP/uninstall-enable-link-boundary.err"
unset HERMESUI_QA_PATH_RACE
rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env" "$SERVICE_STATE"

# Replacing the launcher as enable-link removal enters must preserve the
# foreign unit/link relationship and retry state.
prepare_owned_install
: >"$SERVICE_STATE"
: >"$LOG"
export HERMESUI_QA_PATH_RACE=uninstall_enable_unit_takeover
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/uninstall-enable-unit-entry.out" 2>"$TMP/uninstall-enable-unit-entry.err"; then
  printf 'Uninstall enable-target takeover test unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q 'Description=Foreign unit at link-remove entry' "$TMP/systemd/hermesui-launcher.service"
[[ -L "$ENABLE_LINK" && "$(readlink "$ENABLE_LINK")" == "$TMP/systemd/hermesui-launcher.service" && -e "$TMP/state/install.env" ]]
grep -q 'enable link changed ownership and was preserved' "$TMP/uninstall-enable-unit-entry.err"
unset HERMESUI_QA_PATH_RACE
rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env" "$SERVICE_STATE" "$STOPPED_STATE"

# A launcher takeover at rollback's exact process-stop entry must not cause
# compensation to detach the foreign provider from its inherited link.
rm -f "$ROUTE_STATE" "$ROUTE_FOREIGN_STATE" "$SERVICE_STATE" "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env" "$HERMESUI_QA_FOREIGN_ACTIVE"
export HERMESUI_PORT=18993 HERMESUI_QA_SERVE_MODE=missing HERMESUI_QA_ACTIVE=0
export HERMESUI_QA_TAILNET_HEALTH_FAIL=1 HERMESUI_QA_PROCESS_ENTRY_TAKEOVER=1
if "$ROOT/hermesui/installer/tailnet-setup.sh" >"$TMP/setup-rollback-stop-entry.out" 2>"$TMP/setup-rollback-stop-entry.err"; then
  printf 'Setup rollback process-entry takeover test unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q 'Description=Foreign takeover at process-stop entry' "$TMP/systemd/hermesui-launcher.service"
[[ -L "$ENABLE_LINK" && "$(readlink "$ENABLE_LINK")" == "$TMP/systemd/hermesui-launcher.service" ]]
grep -q 'automatic rollback was incomplete' "$TMP/setup-rollback-stop-entry.err"
unset HERMESUI_QA_TAILNET_HEALTH_FAIL HERMESUI_QA_PROCESS_ENTRY_TAKEOVER
rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env" "$SERVICE_STATE" "$STOPPED_STATE" "$HERMESUI_QA_FOREIGN_ACTIVE"

# Replacing install.env inside the atomic removal helper must preserve the
# replacement even after earlier owned resources were cleaned successfully.
prepare_owned_install
: >"$SERVICE_STATE"
export HERMESUI_QA_PATH_RACE=uninstall_state_rm
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/uninstall-state-remove-boundary.out" 2>"$TMP/uninstall-state-remove-boundary.err"; then
  printf 'Uninstall state removal boundary test unexpectedly succeeded.\n' >&2
  exit 1
fi
grep -q '^FOREIGN_STATE=1$' "$TMP/state/install.env"
[[ ! -e "$TMP/systemd/hermesui-launcher.service" && ! -e "$SERVICE_STATE" ]]
grep -q 'install state could not be removed' "$TMP/uninstall-state-remove-boundary.err"
unset HERMESUI_QA_PATH_RACE
rm -f "$TMP/state/install.env"

# A foreign route appearing after the final status read but inside LocalAPI CAS
# must survive; uninstall keeps state for attended retry and issues no off write.
prepare_owned_install
: >"$ROUTE_STATE"
: >"$SERVICE_STATE"
: >"$LOG"
export HERMESUI_QA_SERVE_MODE=owned HERMESUI_QA_CAS_ROUTE_RACE=1
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/uninstall-route-cas-boundary.out" 2>"$TMP/uninstall-route-cas-boundary.err"; then
  printf 'Uninstall route CAS boundary test unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ -e "$ROUTE_FOREIGN_STATE" && ! -e "$ROUTE_STATE" && -e "$TMP/state/install.env" && ! -e "$TMP/systemd/hermesui-launcher.service" ]]
if grep -q 'set-path=/hermesUI off' "$LOG"; then
  printf 'Route CAS boundary unexpectedly removed the foreign route.\n' >&2
  exit 1
fi
grep -q '/hermesUI Serve route could not be removed' "$TMP/uninstall-route-cas-boundary.err"
unset HERMESUI_QA_CAS_ROUTE_RACE
rm -f "$ROUTE_FOREIGN_STATE" "$TMP/state/install.env" "$SERVICE_STATE"

# Foreground and mixed routes are ambiguous and must fail before mutation.
for mode in foreground_owned mixed_owned mixed_foreign; do
  prepare_owned_install
  : >"$ROUTE_STATE"
  export HERMESUI_QA_SERVE_MODE="$mode" HERMESUI_QA_ACTIVE=1
  before_count="$(python3 - "$LOG" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).read_text().count('set-path=/hermesUI off'))
PY
)"
  if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/${mode}.out" 2>"$TMP/${mode}.err"; then
    printf '%s uninstall ambiguity test unexpectedly succeeded.\n' "$mode" >&2
    exit 1
  fi
  after_count="$(python3 - "$LOG" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).read_text().count('set-path=/hermesUI off'))
PY
)"
  [[ "$before_count" == "$after_count" ]]
  [[ -e "$TMP/systemd/hermesui-launcher.service" && -e "$TMP/state/install.env" && -e "$ROUTE_STATE" ]]
  rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK" "$TMP/state/install.env" "$ROUTE_STATE"
done

# A successful off command is not success unless a post-status read proves removal.
prepare_owned_install
: >"$ROUTE_STATE"
export HERMESUI_QA_SERVE_MODE=post_stuck HERMESUI_QA_ACTIVE=1
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/post-stuck.out" 2>"$TMP/post-stuck.err"; then
  printf 'Post-removal route verification test unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ ! -e "$TMP/systemd/hermesui-launcher.service" && -e "$TMP/state/install.env" ]]
python3 - "$TMP/post-stuck.err" <<'PY'
from pathlib import Path
import sys
assert 'is still configured' in Path(sys.argv[1]).read_text()
assert 'Install state was preserved for retry' in Path(sys.argv[1]).read_text()
PY
rm -f "$TMP/state/install.env" "$ROUTE_STATE"

# Every external cleanup failure must return non-zero and preserve retry state.
prepare_owned_install
export HERMESUI_QA_SERVE_MODE=missing HERMESUI_QA_ACTIVE=1 HERMESUI_QA_SYSTEMCTL_FAIL=stop
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/stop.out" 2>"$TMP/stop.err"; then
  printf 'Owned-process stop failure test unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ -e "$TMP/systemd/hermesui-launcher.service" && -L "$ENABLE_LINK" && -e "$TMP/state/install.env" ]]
unset HERMESUI_QA_SYSTEMCTL_FAIL
rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK"

prepare_owned_install
export HERMESUI_QA_RM_FAIL=unit
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/rm.out" 2>"$TMP/rm.err"; then
  printf 'Unit removal failure test unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ -e "$TMP/systemd/hermesui-launcher.service" && -e "$TMP/state/install.env" ]]
unset HERMESUI_QA_RM_FAIL
rm -f "$TMP/systemd/hermesui-launcher.service" "$ENABLE_LINK"

prepare_owned_install
: >"$ROUTE_STATE"
: >"$SERVICE_STATE"
: >"$HERMESUI_QA_SYSTEMD_CACHE"
: >"$LOG"
export HERMESUI_QA_SERVE_MODE=owned HERMESUI_QA_ACTIVE=1
export HERMESUI_QA_SYSTEMCTL_FAIL=daemon-reload
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/reload-first.out" 2>"$TMP/reload-first.err"; then
  printf 'Daemon-reload failure test unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ ! -e "$TMP/systemd/hermesui-launcher.service" && -e "$TMP/state/install.env" && -e "$ROUTE_STATE" && -e "$HERMESUI_QA_SYSTEMD_CACHE" ]]
grep -q 'systemd user units could not be reloaded' "$TMP/reload-first.err"
unset HERMESUI_QA_SYSTEMCTL_FAIL
export HERMESUI_QA_ACTIVE=0
"$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/reload-retry.out" 2>"$TMP/reload-retry.err"
[[ ! -e "$TMP/state/install.env" && ! -e "$ROUTE_STATE" && ! -e "$HERMESUI_QA_SYSTEMD_CACHE" ]]
[[ "$(grep -c 'systemctl --user daemon-reload' "$LOG")" == "2" ]]
grep -q 'HermesUI uninstall complete' "$TMP/reload-retry.out"

prepare_owned_install
: >"$ROUTE_STATE"
export HERMESUI_QA_TAILSCALE_OFF_FAIL=1
if "$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/off.out" 2>"$TMP/off.err"; then
  printf 'Route removal failure test unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ -e "$ROUTE_STATE" && -e "$TMP/state/install.env" ]]
unset HERMESUI_QA_TAILSCALE_OFF_FAIL
export HERMESUI_QA_ACTIVE=0
"$ROOT/hermesui/installer/tailnet-uninstall.sh" >"$TMP/off-retry.out"
[[ ! -e "$ROUTE_STATE" && ! -e "$TMP/state/install.env" ]]

printf 'Tailnet prerequisite, collision, setup, rerun, status, and failure-injected uninstall tests passed.\n'
