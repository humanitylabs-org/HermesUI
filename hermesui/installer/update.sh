#!/usr/bin/env bash
set -euo pipefail

INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${HERMESUI_REPO_ROOT_OVERRIDE:-$(cd "$INSTALLER_DIR/../.." && pwd)}"
TAG="${1:-}"
EXPECTED_COMMIT="${2:-}"
LOCK_HELPER="${HERMESUI_LIFECYCLE_LOCK_HELPER:-${INSTALLER_DIR}/acquire-lifecycle-lock.py}"
LIFECYCLE_LOCK="${HERMESUI_LIFECYCLE_LOCK_FILE:-${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/hermesui-${UID}/lifecycle.lock}"

[[ "$TAG" =~ ^(exp-)?v[0-9]+\.[0-9]+\.[0-9]+$ && "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
  printf 'Usage: %s vX.Y.Z EXPECTED_40_HEX_COMMIT\n' "$0" >&2
  exit 2
}

if [[ "${HERMESUI_LIFECYCLE_LOCK_HELD:-0}" == "1" ]]; then
  python3 "$LOCK_HELPER" --lock "$LIFECYCLE_LOCK" --fd 9 --verify-inherited || exit 75
else
  exec python3 "$LOCK_HELPER" --lock "$LIFECYCLE_LOCK" --fd 9 -- "$INSTALLER_DIR/update.sh" "$@"
fi

cd "$REPO_ROOT"
[[ -z "$(git status --porcelain)" ]] || {
  printf 'ERROR: Refusing to update a dirty HermesUI checkout. Commit or stash changes first.\n' >&2
  exit 1
}

baseline_commit="$(git rev-parse --verify HEAD)"
baseline_tree="$(git rev-parse --verify 'HEAD^{tree}')"
[[ "$baseline_commit" =~ ^[0-9a-f]{40}$ && "$baseline_tree" =~ ^[0-9a-f]{40}$ ]] || {
  printf 'ERROR: Could not resolve the exact baseline commit/tree.\n' >&2
  exit 1
}
if baseline_branch="$(git symbolic-ref --quiet --short HEAD)"; then
  baseline_mode=branch
else
  baseline_mode=detached
  baseline_branch=''
fi

helper_dir="$(mktemp -d "${TMPDIR:-/tmp}/hermesui-update-helper.XXXXXX")"
tag_ref="refs/hermesui-update/tag-$$"
for helper in tailnet-setup.sh acquire-lifecycle-lock.py stop-owned-process.py systemd-start-owned.py systemd-launcher-unit.py runtime-home-guard.py owned-path-op.py; do
  cp "$INSTALLER_DIR/$helper" "$helper_dir/$helper"
done
chmod 0700 "$helper_dir/tailnet-setup.sh"
chmod 0600 "$helper_dir/"*.py
LOCK_HELPER="$helper_dir/acquire-lifecycle-lock.py"

runtime_operation() {
  local operation="$1" commit="$2" tree="$3"
  HERMESUI_REPO_ROOT_OVERRIDE="$REPO_ROOT" \
  HERMESUI_RUNTIME_OPERATION="$operation" \
  HERMESUI_EXPECTED_RUNTIME_COMMIT="$commit" \
  HERMESUI_EXPECTED_RUNTIME_TREE="$tree" \
  HERMESUI_LIFECYCLE_LOCK_HELD=1 \
  HERMESUI_LIFECYCLE_LOCK_HELPER="$LOCK_HELPER" \
  HERMESUI_PROCESS_STOP="$helper_dir/stop-owned-process.py" \
  HERMESUI_SERVICE_START="$helper_dir/systemd-start-owned.py" \
  HERMESUI_LAUNCHER_UNIT_HELPER="$helper_dir/systemd-launcher-unit.py" \
  HERMESUI_PATH_OP="$helper_dir/owned-path-op.py" \
  bash "$helper_dir/tailnet-setup.sh"
}

baseline_runtime=''
checkout_changed=0
update_complete=0
rollback_in_progress=0
candidate_tree=''

cleanup_refs() {
  git update-ref -d "$tag_ref" >/dev/null 2>&1 || true
  rm -rf "$helper_dir"
}

restore_checkout() {
  if [[ "$baseline_mode" == branch ]]; then
    git checkout -q "$baseline_branch" || return 1
  else
    git checkout -q --detach "$baseline_commit" || return 1
  fi
  [[ "$(git rev-parse HEAD)" == "$baseline_commit" && "$(git rev-parse 'HEAD^{tree}')" == "$baseline_tree" ]]
}

rollback_update() {
  local status=$?
  [[ "$update_complete" == "1" ]] && { cleanup_refs; return "$status"; }
  [[ "$rollback_in_progress" == "0" ]] || return "$status"
  rollback_in_progress=1
  trap - EXIT
  set +e

  if [[ "$checkout_changed" == "1" && "$(git rev-parse HEAD 2>/dev/null)" == "$EXPECTED_COMMIT" ]]; then
    runtime_operation ensure-inactive "$EXPECTED_COMMIT" "$candidate_tree" >/dev/null 2>&1
    candidate_stop_status=$?
    if [[ "$candidate_stop_status" != "0" ]]; then
      printf 'ERROR: Candidate runtime could not be authoritatively stopped; checkout and recovery evidence were preserved.\n' >&2
      cleanup_refs
      exit "$status"
    fi
  fi

  if ! restore_checkout; then
    printf 'ERROR: Update failed and the exact baseline checkout could not be restored. Recovery is incomplete.\n' >&2
    cleanup_refs
    exit "$status"
  fi
  checkout_changed=0

  baseline_restore_status=0
  if [[ "$baseline_runtime" == active ]]; then
    runtime_operation ensure-active "$baseline_commit" "$baseline_tree" >/dev/null 2>&1 || baseline_restore_status=$?
  elif [[ "$baseline_runtime" == inactive ]]; then
    runtime_operation ensure-inactive "$baseline_commit" "$baseline_tree" >/dev/null 2>&1 || baseline_restore_status=$?
  else
    baseline_restore_status=1
  fi
  if [[ "$baseline_restore_status" == "0" ]]; then
    printf 'ERROR: Update failed; restored previous checkout and exact %s runtime state.\n' "$baseline_runtime" >&2
    cleanup_refs
    exit "$status"
  fi

  printf 'ERROR: Update failed; checkout was restored but the exact prior runtime state was not. Recovery is incomplete.\n' >&2
  cleanup_refs
  exit "$status"
}
trap rollback_update EXIT

remote_identity="$(git ls-remote origin "refs/tags/$TAG" "refs/tags/$TAG^{}")"
read -r remote_tag_oid remote_commit < <(python3 - "$remote_identity" "$TAG" <<'PY'
import re
import sys
raw, tag = sys.argv[1:]
oid = re.compile(r'^[0-9a-f]{40}$')
refs = {}
for line in raw.splitlines():
    value, separator, ref = line.partition('\t')
    if separator != '\t' or not oid.fullmatch(value) or ref in refs:
        raise SystemExit(1)
    refs[ref] = value
raw_ref = f'refs/tags/{tag}'
peeled_ref = f'{raw_ref}^{{}}'
if set(refs) != {raw_ref, peeled_ref}:
    raise SystemExit(1)
print(refs[raw_ref], refs[peeled_ref])
PY
) || {
  printf 'ERROR: Remote release tag is missing, lightweight, duplicate, or malformed.\n' >&2
  exit 1
}
[[ "$remote_commit" == "$EXPECTED_COMMIT" ]] || {
  printf 'ERROR: %s resolves to %s, not reviewed commit %s. Nothing was changed.\n' "$TAG" "$remote_commit" "$EXPECTED_COMMIT" >&2
  exit 1
}
git fetch --no-tags origin "refs/tags/$TAG:$tag_ref"
[[ "$(git cat-file -t "$tag_ref")" == tag ]]
[[ "$(git rev-parse "$tag_ref")" == "$remote_tag_oid" ]]
[[ "$(git rev-parse "$tag_ref^{commit}")" == "$EXPECTED_COMMIT" ]]
candidate_tree="$(git rev-parse "$EXPECTED_COMMIT^{tree}")"
[[ "$candidate_tree" =~ ^[0-9a-f]{40}$ ]]

baseline_runtime="$(runtime_operation probe "$baseline_commit" "$baseline_tree")" || {
  printf 'ERROR: Could not authoritatively record the exact baseline runtime state. Nothing was changed.\n' >&2
  exit 1
}
[[ "$baseline_runtime" == active || "$baseline_runtime" == inactive ]] || {
  printf 'ERROR: Baseline runtime probe returned an unsupported state. Nothing was changed.\n' >&2
  exit 1
}
if [[ "$baseline_runtime" == active ]]; then
  [[ "$(runtime_operation stop "$baseline_commit" "$baseline_tree")" == inactive ]] || {
    printf 'ERROR: Could not safely quiesce the exact baseline runtime. Nothing was changed.\n' >&2
    exit 1
  }
fi

git checkout -q --detach "$EXPECTED_COMMIT"
checkout_changed=1
[[ "$(git rev-parse HEAD)" == "$EXPECTED_COMMIT" && "$(git rev-parse 'HEAD^{tree}')" == "$candidate_tree" ]]

HERMESUI_LIFECYCLE_LOCK_HELD=1 \
HERMESUI_LIFECYCLE_LOCK_HELPER="$LOCK_HELPER" \
HERMESUI_DEFER_SERVICE_RESTORE=1 \
  "$INSTALLER_DIR/tailnet-setup.sh"

[[ "$(git rev-parse HEAD)" == "$EXPECTED_COMMIT" && "$(git rev-parse 'HEAD^{tree}')" == "$candidate_tree" ]]
[[ "$(runtime_operation probe "$EXPECTED_COMMIT" "$candidate_tree")" == active ]]
update_complete=1
trap - EXIT
cleanup_refs
printf 'HermesUI updated to %s at reviewed commit %s (tree %s).\n' "$TAG" "$EXPECTED_COMMIT" "$candidate_tree"
