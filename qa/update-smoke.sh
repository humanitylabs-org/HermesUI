#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

WORK="$TMP/work"
ORIGIN="$TMP/origin.git"
RUNTIME="$TMP/running-version"
RUNTIME_IDENTITY="$TMP/running-identity"
RUNTIME_STATE="$TMP/running-state"
SETUP_LOG="$TMP/setup.log"
export HERMESUI_QA_RUNTIME_FILE="$RUNTIME"
export HERMESUI_QA_RUNTIME_IDENTITY_FILE="$RUNTIME_IDENTITY"
export HERMESUI_QA_RUNTIME_STATE_FILE="$RUNTIME_STATE"
export HERMESUI_QA_SETUP_LOG="$SETUP_LOG"
export HERMESUI_LIFECYCLE_LOCK_FILE="$TMP/lifecycle/lifecycle.lock"

mkdir -p "$WORK/hermesui/installer"
git init -q -b main "$WORK"
git -C "$WORK" config user.name 'HermesUI Update QA'
git -C "$WORK" config user.email 'update-qa@example.invalid'
for helper in \
  acquire-lifecycle-lock.py \
  owned-path-op.py \
  stop-owned-process.py \
  systemd-launcher-unit.py \
  systemd-start-owned.py \
  update.sh; do
  cp "$ROOT/hermesui/installer/$helper" "$WORK/hermesui/installer/$helper"
done

write_setup_fixture() {
  local exit_status="$1"
  cat >"$WORK/hermesui/installer/tailnet-setup.sh" <<SH
#!/usr/bin/env bash
set -euo pipefail
root="\${HERMESUI_REPO_ROOT_OVERRIDE:-\$(cd "\$(dirname "\${BASH_SOURCE[0]}")/../.." && pwd)}"
head="\$(git -C "\$root" rev-parse HEAD)"
tree="\$(git -C "\$root" rev-parse 'HEAD^{tree}')"
operation="\${HERMESUI_RUNTIME_OPERATION:-normal}"
printf 'setup mode=%s head=%s tree=%s\\n' "\$operation" "\$head" "\$tree" >>"\$HERMESUI_QA_SETUP_LOG"
if [[ "\$operation" != normal ]]; then
  [[ "\${HERMESUI_EXPECTED_RUNTIME_COMMIT:-}" == "\$head" ]]
  [[ "\${HERMESUI_EXPECTED_RUNTIME_TREE:-}" == "\$tree" ]]
  case "\$operation" in
    probe)
      cat "\$HERMESUI_QA_RUNTIME_STATE_FILE"
      ;;
    stop|ensure-inactive)
      printf 'inactive\\n' >"\$HERMESUI_QA_RUNTIME_STATE_FILE"
      printf 'inactive\\n'
      ;;
    ensure-active)
      cat "\$root/VERSION" >"\$HERMESUI_QA_RUNTIME_FILE"
      printf '%s:%s\\n' "\$head" "\$tree" >"\$HERMESUI_QA_RUNTIME_IDENTITY_FILE"
      printf 'active\\n' >"\$HERMESUI_QA_RUNTIME_STATE_FILE"
      printf 'active\\n'
      ;;
    *) exit 91 ;;
  esac
  exit 0
fi
cat "\$root/VERSION" >"\$HERMESUI_QA_RUNTIME_FILE"
printf '%s:%s\\n' "\$head" "\$tree" >"\$HERMESUI_QA_RUNTIME_IDENTITY_FILE"
printf 'active\\n' >"\$HERMESUI_QA_RUNTIME_STATE_FILE"
exit $exit_status
SH
  chmod +x "$WORK/hermesui/installer/tailnet-setup.sh"
}

write_setup_fixture 0
printf 'base\n' >"$WORK/VERSION"
chmod +x "$WORK/hermesui/installer/"*
git -C "$WORK" add .
git -C "$WORK" commit -q -m base
base_commit="$(git -C "$WORK" rev-parse HEAD)"
base_tree="$(git -C "$WORK" rev-parse 'HEAD^{tree}')"

git -C "$WORK" switch -q -c release-fixtures
write_setup_fixture 23
printf 'failed-target\n' >"$WORK/VERSION"
git -C "$WORK" add .
git -C "$WORK" commit -q -m 'failing release fixture'
failure_commit="$(git -C "$WORK" rev-parse HEAD)"
git -C "$WORK" tag -a v9.9.9 -m 'failing fixture'

write_setup_fixture 0
printf 'successful-target\n' >"$WORK/VERSION"
git -C "$WORK" add .
git -C "$WORK" commit -q -m 'successful release fixture'
success_commit="$(git -C "$WORK" rev-parse HEAD)"
git -C "$WORK" tag -a v9.9.8 -m 'successful fixture'
git -C "$WORK" tag -a v9.9.7 "$failure_commit" -m 'mismatched fixture'

git -C "$WORK" switch -q main
git clone -q --bare "$WORK" "$ORIGIN"
git -C "$WORK" remote add origin "$ORIGIN"
printf 'base\n' >"$RUNTIME"
printf '%s:%s\n' "$base_commit" "$base_tree" >"$RUNTIME_IDENTITY"
printf 'active\n' >"$RUNTIME_STATE"
: >"$SETUP_LOG"

if "$WORK/hermesui/installer/update.sh" v9.9.7 "$success_commit" >"$TMP/moved.out" 2>"$TMP/moved.err"; then
  printf 'Moved-tag negative control unexpectedly succeeded.\n' >&2
  exit 1
fi
[[ "$(git -C "$WORK" symbolic-ref --short HEAD)" == main ]]
[[ "$(git -C "$WORK" rev-parse HEAD)" == "$base_commit" ]]
[[ "$(cat "$RUNTIME_STATE")" == active ]]
[[ ! -s "$SETUP_LOG" ]]
grep -q 'not reviewed commit' "$TMP/moved.err"

if "$WORK/hermesui/installer/update.sh" v9.9.9 "$failure_commit" >"$TMP/branch-fail.out" 2>"$TMP/branch-fail.err"; then
  printf 'Branch update failure test unexpectedly succeeded.\n' >&2
  exit 1
else
  status=$?
fi
[[ "$status" == 23 ]]
[[ "$(git -C "$WORK" symbolic-ref --short HEAD)" == main ]]
[[ "$(git -C "$WORK" rev-parse HEAD)" == "$base_commit" ]]
[[ "$(git -C "$WORK" rev-parse 'HEAD^{tree}')" == "$base_tree" ]]
[[ "$(cat "$WORK/VERSION")" == base ]]
[[ "$(cat "$RUNTIME")" == base ]]
[[ "$(cat "$RUNTIME_IDENTITY")" == "$base_commit:$base_tree" ]]
[[ "$(cat "$RUNTIME_STATE")" == active ]]
grep -q 'setup mode=stop head='"$base_commit" "$SETUP_LOG"
grep -q 'setup mode=normal head='"$failure_commit" "$SETUP_LOG"
grep -q 'setup mode=ensure-inactive head='"$failure_commit" "$SETUP_LOG"
grep -q 'setup mode=ensure-active head='"$base_commit" "$SETUP_LOG"
grep -q 'restored previous checkout and exact active runtime state' "$TMP/branch-fail.err"

: >"$SETUP_LOG"
git -C "$WORK" checkout -q --detach "$base_commit"
if "$WORK/hermesui/installer/update.sh" v9.9.9 "$failure_commit" >"$TMP/detached-fail.out" 2>"$TMP/detached-fail.err"; then
  printf 'Detached update failure test unexpectedly succeeded.\n' >&2
  exit 1
else
  status=$?
fi
[[ "$status" == 23 ]]
if git -C "$WORK" symbolic-ref --quiet HEAD >/dev/null; then
  printf 'Expected a detached checkout.\n' >&2
  exit 1
fi
[[ "$(git -C "$WORK" rev-parse HEAD)" == "$base_commit" ]]
[[ "$(cat "$RUNTIME_STATE")" == active ]]
grep -q 'restored previous checkout and exact active runtime state' "$TMP/detached-fail.err"

# An inactive baseline stays inactive after a failed update; recovery never
# starts a service that was deliberately stopped before the update.
: >"$SETUP_LOG"
printf 'inactive\n' >"$RUNTIME_STATE"
git -C "$WORK" switch -q main
if "$WORK/hermesui/installer/update.sh" v9.9.9 "$failure_commit" >"$TMP/inactive-fail.out" 2>"$TMP/inactive-fail.err"; then
  printf 'Inactive-baseline failure test unexpectedly succeeded.\n' >&2
  exit 1
else
  status=$?
fi
[[ "$status" == 23 ]]
[[ "$(git -C "$WORK" symbolic-ref --short HEAD)" == main ]]
[[ "$(cat "$RUNTIME_STATE")" == inactive ]]
grep -q 'setup mode=ensure-inactive head='"$base_commit" "$SETUP_LOG"
grep -q 'restored previous checkout and exact inactive runtime state' "$TMP/inactive-fail.err"

: >"$SETUP_LOG"
printf 'active\n' >"$RUNTIME_STATE"
"$WORK/hermesui/installer/update.sh" v9.9.8 "$success_commit" >"$TMP/success.out" 2>"$TMP/success.err"
if git -C "$WORK" symbolic-ref --quiet HEAD >/dev/null; then
  printf 'Expected a detached checkout.\n' >&2
  exit 1
fi
[[ "$(git -C "$WORK" rev-parse HEAD)" == "$success_commit" ]]
[[ "$(cat "$WORK/VERSION")" == successful-target ]]
[[ "$(cat "$RUNTIME")" == successful-target ]]
[[ "$(cat "$RUNTIME_IDENTITY")" == "$(git -C "$WORK" rev-parse HEAD):$(git -C "$WORK" rev-parse 'HEAD^{tree}')" ]]
[[ "$(cat "$RUNTIME_STATE")" == active ]]
grep -q 'setup mode=normal head='"$success_commit" "$SETUP_LOG"

printf 'Reviewed annotated-tag binding, locked quiesce, exact active/inactive rollback, and success tests passed.\n'
