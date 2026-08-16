#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG="${1:-}"
LIFECYCLE_LOCK="${HERMESUI_LIFECYCLE_LOCK_FILE:-/tmp/hermesui-${UID}.lifecycle.lock}"

if [[ "${HERMESUI_LIFECYCLE_LOCK_HELD:-0}" == "1" ]]; then
  [[ "$(readlink "/proc/$$/fd/9" 2>/dev/null || true)" == "$LIFECYCLE_LOCK" ]] || {
    printf 'ERROR: inherited HermesUI lifecycle lock is invalid.\n' >&2
    exit 75
  }
else
  exec 9>"$LIFECYCLE_LOCK"
  export HERMESUI_LIFECYCLE_LOCK_HELD=1
fi
flock -n 9 || {
  printf 'ERROR: another HermesUI setup, update, or uninstall is already running.\n' >&2
  exit 75
}

[[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { printf 'Usage: ./scripts/update.sh vX.Y.Z\n' >&2; exit 2; }
cd "$REPO_ROOT"

if [[ -n "$(git status --porcelain)" ]]; then
  printf 'ERROR: Refusing to update a checkout with local changes.\n' >&2
  exit 1
fi

git fetch origin tag "$TAG" --force
git rev-parse --verify "refs/tags/$TAG^{commit}" >/dev/null
previous_commit="$(git rev-parse HEAD)"
previous_branch="$(git symbolic-ref --quiet --short HEAD || true)"

rollback_checkout() {
  status=$?
  trap - EXIT
  if [[ "$status" != "0" ]]; then
    printf 'ERROR: update setup failed; restoring the previous checkout.\n' >&2
    if [[ -n "$previous_branch" ]]; then
      git checkout --quiet "$previous_branch" || { printf 'ERROR: failed to restore branch %s; checkout remains at %s.\n' "$previous_branch" "$(git rev-parse HEAD)" >&2; exit "$status"; }
    else
      git checkout --quiet --detach "$previous_commit" || { printf 'ERROR: failed to restore detached commit %s; checkout remains at %s.\n' "$previous_commit" "$(git rev-parse HEAD)" >&2; exit "$status"; }
    fi
    if [[ "$(git rev-parse HEAD)" != "$previous_commit" ]]; then
      printf 'ERROR: checkout rollback did not restore %s; checkout is at %s.\n' "$previous_commit" "$(git rev-parse HEAD)" >&2
      exit "$status"
    fi
    if ! "$REPO_ROOT/scripts/tailnet-setup.sh"; then
      printf 'ERROR: restored checkout %s, but failed to restore its running HermesUI service.\n' "$previous_commit" >&2
      exit "$status"
    fi
    printf 'OK: restored previous checkout and running service at %s.\n' "$previous_commit" >&2
  fi
  exit "$status"
}

trap rollback_checkout EXIT
git checkout --detach "$TAG"
[[ "$(git describe --tags --exact-match)" == "$TAG" ]]
"$REPO_ROOT/scripts/tailnet-setup.sh"
trap - EXIT
