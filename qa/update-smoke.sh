#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

WORK="$TMP/work"
ORIGIN="$TMP/origin.git"
RUNTIME="$TMP/running-version"
export HERMESUI_QA_RUNTIME_FILE="$RUNTIME"
git init -q -b main "$WORK"
git -C "$WORK" config user.name 'HermesUI Update QA'
git -C "$WORK" config user.email 'update-qa@example.invalid'
mkdir -p "$WORK/scripts"
cp "$ROOT/scripts/update.sh" "$WORK/scripts/update.sh"
# shellcheck disable=SC2016 # Expand this fixture variable only when the generated script runs.
printf '#!/usr/bin/env bash\ncat VERSION >"$HERMESUI_QA_RUNTIME_FILE"\nexit 0\n' >"$WORK/scripts/tailnet-setup.sh"
printf 'base\n' >"$WORK/VERSION"
chmod +x "$WORK/scripts/update.sh" "$WORK/scripts/tailnet-setup.sh"
git -C "$WORK" add .
git -C "$WORK" commit -q -m base
base_commit="$(git -C "$WORK" rev-parse HEAD)"

git -C "$WORK" switch -q -c release-fixtures
# shellcheck disable=SC2016 # Expand this fixture variable only when the generated script runs.
printf '#!/usr/bin/env bash\ncat VERSION >"$HERMESUI_QA_RUNTIME_FILE"\nexit 23\n' >"$WORK/scripts/tailnet-setup.sh"
printf 'failed-target\n' >"$WORK/VERSION"
git -C "$WORK" add .
git -C "$WORK" commit -q -m 'failing release fixture'
git -C "$WORK" tag v9.9.9

# shellcheck disable=SC2016 # Expand this fixture variable only when the generated script runs.
printf '#!/usr/bin/env bash\ncat VERSION >"$HERMESUI_QA_RUNTIME_FILE"\nexit 0\n' >"$WORK/scripts/tailnet-setup.sh"
printf 'successful-target\n' >"$WORK/VERSION"
git -C "$WORK" add .
git -C "$WORK" commit -q -m 'successful release fixture'
git -C "$WORK" tag v9.9.8
success_commit="$(git -C "$WORK" rev-parse HEAD)"

git -C "$WORK" switch -q main
git clone -q --bare "$WORK" "$ORIGIN"
git -C "$WORK" remote add origin "$ORIGIN"
printf 'base\n' >"$RUNTIME"

if "$WORK/scripts/update.sh" v9.9.9 >"$TMP/branch-fail.out" 2>"$TMP/branch-fail.err"; then
  printf 'Branch update failure test unexpectedly succeeded.\n' >&2
  exit 1
else
  status=$?
fi
[[ "$status" == "23" ]]
[[ "$(git -C "$WORK" symbolic-ref --short HEAD)" == "main" ]]
[[ "$(git -C "$WORK" rev-parse HEAD)" == "$base_commit" ]]
[[ "$(cat "$WORK/VERSION")" == "base" ]]
[[ "$(cat "$RUNTIME")" == "base" ]]
grep -q 'restored previous checkout and running service' "$TMP/branch-fail.err"

git -C "$WORK" checkout -q --detach "$base_commit"
if "$WORK/scripts/update.sh" v9.9.9 >"$TMP/detached-fail.out" 2>"$TMP/detached-fail.err"; then
  printf 'Detached update failure test unexpectedly succeeded.\n' >&2
  exit 1
else
  status=$?
fi
[[ "$status" == "23" ]]
if git -C "$WORK" symbolic-ref --quiet HEAD >/dev/null; then
  printf 'Detached rollback unexpectedly restored a branch.\n' >&2
  exit 1
fi
[[ "$(git -C "$WORK" rev-parse HEAD)" == "$base_commit" ]]
[[ "$(cat "$WORK/VERSION")" == "base" ]]
[[ "$(cat "$RUNTIME")" == "base" ]]
grep -q 'restored previous checkout and running service' "$TMP/detached-fail.err"

git -C "$WORK" switch -q main
"$WORK/scripts/update.sh" v9.9.8 >"$TMP/success.out" 2>"$TMP/success.err"
if git -C "$WORK" symbolic-ref --quiet HEAD >/dev/null; then
  printf 'Successful tagged update did not leave a detached checkout.\n' >&2
  exit 1
fi
[[ "$(git -C "$WORK" rev-parse HEAD)" == "$success_commit" ]]
[[ "$(git -C "$WORK" describe --tags --exact-match)" == "v9.9.8" ]]
[[ "$(cat "$WORK/VERSION")" == "successful-target" ]]
[[ "$(cat "$RUNTIME")" == "successful-target" ]]

printf 'Update checkout rollback and success tests passed.\n'
