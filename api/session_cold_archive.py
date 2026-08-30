"""Crash-safe cold storage for settled native WebUI sessions.

Archived transcripts and attachments live outside the hot ``sessions`` tree.
The hot sidecar is replaced by a compact metadata stub so sidebar enumeration
stays cheap. Run/turn journals are intentionally discarded after a verified
cold package commits; they are recovery artifacts, not conversation records.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import threading
import time
import uuid
import weakref
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

ARCHIVE_SCHEMA = 1
_MANIFEST_NAME = "manifest.json"
_SESSION_NAME = "session.json"
_SOURCE_BACKUP_NAME = "source-backup.json"
_PREVIOUS_SESSION_NAME = ".previous-session.json"
_HEAVY_STUB_FIELDS = {
    "messages",
    "context_messages",
    "tool_calls",
    "anchor_activity_scenes",
}
_EXTERNAL_SOURCES = {
    "api",
    "cli",
    "cron",
    "discord",
    "email",
    "gateway",
    "msteams",
    "signal",
    "slack",
    "subagent",
    "telegram",
    "tui",
    "whatsapp",
}

_STORAGE_LOCKS_GUARD = threading.Lock()
_STORAGE_LOCKS: weakref.WeakValueDictionary[str, threading.RLock] = weakref.WeakValueDictionary()
_LIVE_GENERATIONS: dict[str, str] = {}


@contextmanager
def session_storage_lock(session_id: str):
    """Serialize hot/cold publication with every in-process Session.save()."""
    if not _models().is_safe_session_id(session_id):
        raise ValueError(f"Unsafe session_id {session_id!r}")
    with _STORAGE_LOCKS_GUARD:
        lock = _STORAGE_LOCKS.get(session_id)
        if lock is None:
            lock = threading.RLock()
            _STORAGE_LOCKS[session_id] = lock
    with lock:
        yield


class ColdArchiveError(RuntimeError):
    """The cold package could not be committed or verified safely."""


class ActiveSessionArchiveError(ColdArchiveError):
    """A session still has work capable of writing to it."""


def _models():
    from api import models

    return models


def cold_archive_root() -> Path:
    """Return the same-filesystem cold root for the active state directory."""
    return _models().SESSION_DIR.parent / "cold_archive" / "sessions"


def cold_archive_package_path(session_id: str) -> Path:
    models = _models()
    if not models.is_safe_session_id(session_id):
        raise ValueError(f"Unsafe session_id {session_id!r}")
    root = cold_archive_root().resolve()
    package = (root / session_id).resolve()
    if not package.is_relative_to(root):
        raise ValueError(f"Unsafe session_id {session_id!r}")
    return package


def _hot_cold_marker(session_id: str) -> dict | None:
    models = _models()
    path = models.SESSION_DIR / f"{session_id}.json"
    if not path.is_file():
        return None
    try:
        prefix = models._read_metadata_json_prefix(path)
        payload = json.loads(prefix) if prefix else json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    marker = payload.get("cold_archive") if isinstance(payload, dict) else None
    return marker if isinstance(marker, dict) else None


def prepare_session_save(session) -> None:
    """Redirect or reject stale saves that race a storage-tier transition."""
    session_id = session.session_id
    package = cold_archive_package_path(session_id)
    marker = _hot_cold_marker(session_id) if package.is_dir() else None
    if marker is not None:
        try:
            manifest = json.loads((package / _MANIFEST_NAME).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ColdArchiveError(f"Cold archive manifest for {session_id} is unreadable") from exc
        expected = manifest.get("generation")
        actual = getattr(session, "cold_archive_generation", None)
        if not expected or actual != expected:
            raise ColdArchiveError(
                f"Refusing stale save for {session_id} across a cold-archive transition"
            )
        session._cold_archive_ref = marker
        session._cold_archived = True
        return

    expected_live = _LIVE_GENERATIONS.get(session_id)
    if expected_live and getattr(session, "cold_archive_generation", None) != expected_live:
        raise ColdArchiveError(
            f"Refusing stale save for {session_id} after cold-archive restoration"
        )


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}")
    try:
        with open(tmp, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _atomic_write_json(path: Path, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    _atomic_write_bytes(path, data)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(path: Path) -> dict:
    return {"sha256": _sha256(path), "size": path.stat().st_size}


def _assert_no_symlink_components(path: Path, root: Path) -> None:
    current = path
    while current != root:
        if current.is_symlink():
            raise ColdArchiveError(
                f"Cold archive storage contains a symbolic link: {current}"
            )
        parent = current.parent
        if parent == current:
            raise ColdArchiveError(f"Unsafe cold archive path: {path}")
        current = parent


def _assert_tree_has_no_symlinks(root: Path) -> None:
    if root.is_symlink():
        raise ColdArchiveError(f"Session attachments cannot be a symbolic link: {root}")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ColdArchiveError(
                f"Session attachments contain a symbolic link: {path}"
            )


def _manifest_files(package: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for path in sorted(package.rglob("*")):
        if not path.is_file() or path in {
            package / _MANIFEST_NAME,
            package / _PREVIOUS_SESSION_NAME,
        }:
            continue
        rel = path.relative_to(package).as_posix()
        records[rel] = _file_record(path)
    return records


def _write_manifest(
    package: Path,
    session_id: str,
    *,
    created_at: float | None = None,
    generation: str | None = None,
) -> dict:
    manifest = {
        "schema": ARCHIVE_SCHEMA,
        "session_id": session_id,
        "generation": generation or uuid.uuid4().hex,
        "created_at": created_at or time.time(),
        "files": _manifest_files(package),
        "journals": "discarded_after_commit",
    }
    _atomic_write_json(package / _MANIFEST_NAME, manifest)
    return manifest


def _verify_package(session_id: str) -> tuple[Path, dict]:
    package = cold_archive_package_path(session_id)
    manifest_path = package / _MANIFEST_NAME
    if not package.is_dir() or not manifest_path.is_file():
        raise ColdArchiveError(f"Cold archive for {session_id} is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ColdArchiveError(f"Cold archive manifest for {session_id} is unreadable") from exc
    if (
        manifest.get("schema") != ARCHIVE_SCHEMA
        or manifest.get("session_id") != session_id
        or not isinstance(manifest.get("generation"), str)
        or not manifest.get("generation")
    ):
        raise ColdArchiveError(f"Cold archive manifest for {session_id} is incompatible")
    files = manifest.get("files")
    if not isinstance(files, dict) or _SESSION_NAME not in files:
        raise ColdArchiveError(f"Cold archive manifest for {session_id} is incomplete")

    def _record_matches(path: Path, record: object) -> bool:
        if not path.is_file() or not isinstance(record, dict):
            return False
        return path.stat().st_size == record.get("size") and _sha256(path) == record.get("sha256")

    session_path = package / _SESSION_NAME
    session_record = files[_SESSION_NAME]
    previous = package / _PREVIOUS_SESSION_NAME
    if not _record_matches(session_path, session_record):
        # A metadata update writes the new session before the new manifest. If a
        # crash lands between those atomic writes, the previous file is the exact
        # payload referenced by the old manifest and can be restored losslessly.
        if _record_matches(previous, session_record):
            os.replace(previous, session_path)
            _fsync_dir(package)
        else:
            raise ColdArchiveError(f"Cold archive transcript for {session_id} failed verification")
    else:
        previous.unlink(missing_ok=True)

    for rel, record in files.items():
        unresolved = package / rel
        _assert_no_symlink_components(unresolved, package)
        candidate = unresolved.resolve()
        if not candidate.is_relative_to(package.resolve()) or not _record_matches(candidate, record):
            raise ColdArchiveError(f"Cold archive artifact {rel!r} for {session_id} failed verification")
    return package, manifest


def _native_webui_session(session) -> bool:
    if bool(getattr(session, "read_only", False) or getattr(session, "is_cli_session", False)):
        return False
    try:
        from api.agent_sessions import MESSAGING_SOURCES

        external_sources = _EXTERNAL_SOURCES | {
            str(source).strip().lower() for source in MESSAGING_SOURCES
        }
    except ImportError:
        external_sources = _EXTERNAL_SOURCES
    for attr in ("source_tag", "raw_source", "session_source", "source_label", "source"):
        source = str(getattr(session, attr, "") or "").strip().lower()
        if source in external_sources or source == "messaging":
            return False
    if any(getattr(session, attr, None) for attr in ("chat_id", "thread_id", "platform", "session_key")):
        return False
    return True


def _assert_settled(session) -> None:
    if any(
        (
            getattr(session, "active_stream_id", None),
            getattr(session, "pending_user_message", None),
            getattr(session, "pending_started_at", None),
            getattr(session, "pending_attachments", None),
        )
    ):
        raise ActiveSessionArchiveError("Session is active or has a pending turn")
    try:
        from api.config import ACTIVE_RUNS, ACTIVE_RUNS_LOCK, session_writeback_owner

        if session_writeback_owner(session.session_id):
            raise ActiveSessionArchiveError("Session still has an active writeback owner")
        with ACTIVE_RUNS_LOCK:
            entries = list(ACTIVE_RUNS.values())
        for entry in entries:
            if isinstance(entry, dict) and str(entry.get("session_id") or "") == session.session_id:
                raise ActiveSessionArchiveError("Session still has an active worker")
    except ActiveSessionArchiveError:
        raise
    except ImportError:
        # Model-only tools/tests may not import the runtime registry. Persisted
        # pending/stream fields remain the minimum fail-closed guard.
        pass


def _attachment_dir(session_id: str) -> Path:
    from api.upload import _session_attachment_dir

    return _session_attachment_dir(session_id)


def _tree_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _copy_tree(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, copy_function=shutil.copy2)
        for path in destination.rglob("*"):
            if path.is_file():
                with open(path, "rb") as handle:
                    os.fsync(handle.fileno())
        for directory in sorted((p for p in destination.rglob("*") if p.is_dir()), reverse=True):
            _fsync_dir(directory)
        _fsync_dir(destination)


def _trees_match(source: Path, destination: Path) -> bool:
    """Return whether two attachment trees have the same files and bytes."""
    if not source.is_dir() or not destination.is_dir():
        return False
    if any(path.is_symlink() for path in source.rglob("*")):
        return False
    if any(path.is_symlink() for path in destination.rglob("*")):
        return False
    source_files = {
        path.relative_to(source).as_posix(): path
        for path in source.rglob("*")
        if path.is_file()
    }
    destination_files = {
        path.relative_to(destination).as_posix(): path
        for path in destination.rglob("*")
        if path.is_file()
    }
    if source_files.keys() != destination_files.keys():
        return False
    return all(
        source_path.stat().st_size == destination_files[rel].stat().st_size
        and _sha256(source_path) == _sha256(destination_files[rel])
        for rel, source_path in source_files.items()
    )


def _copy_file_durable(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(f".{destination.name}.tmp.{uuid.uuid4().hex}")
    try:
        with open(source, "rb") as src, open(tmp, "xb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        shutil.copystat(source, tmp, follow_symlinks=True)
        os.replace(tmp, destination)
        _fsync_dir(destination.parent)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _stub_from_payload(
    payload: dict,
    manifest: dict,
    *,
    cleanup_complete: bool = False,
) -> dict:
    stub = {key: value for key, value in payload.items() if key not in _HEAVY_STUB_FIELDS}
    stub["archived"] = True
    stub["message_count"] = len(payload.get("messages") or [])
    stub["cold_archive"] = {
        "version": ARCHIVE_SCHEMA,
        "generation": manifest["generation"],
        "cleanup_complete": cleanup_complete,
        "message_count": stub["message_count"],
        "session_sha256": manifest["files"][_SESSION_NAME]["sha256"],
    }
    # Keep the empty sentinel last: load_metadata_only() stops before this key
    # and never opens the cold transcript, while a normal load sees the marker
    # above and resolves the verified package.
    stub["messages"] = []
    return stub


def _write_stub(session, payload: dict, manifest: dict) -> None:
    prior_marker = getattr(session, "_cold_archive_ref", None)
    cleanup_complete = bool(
        isinstance(prior_marker, dict) and prior_marker.get("cleanup_complete") is True
    )
    stub = _stub_from_payload(
        payload,
        manifest,
        cleanup_complete=cleanup_complete,
    )
    _atomic_write_json(session.path, stub)
    session.archived = True
    session._metadata_message_count = stub["message_count"]
    session.cold_archive_generation = manifest["generation"]
    session._cold_archive_ref = stub["cold_archive"]
    session._cold_archived = True


def _mark_hot_cleanup_complete(session_id: str, *, session=None) -> None:
    path = _models().SESSION_DIR / f"{session_id}.json"
    try:
        stub = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ColdArchiveError(f"Cold archive stub for {session_id} is unreadable") from exc
    marker = stub.get("cold_archive")
    if not isinstance(marker, dict):
        raise ColdArchiveError(f"Cold archive stub for {session_id} is missing its marker")
    marker = dict(marker)
    marker["cleanup_complete"] = True
    stub["cold_archive"] = marker
    _atomic_write_json(path, stub)
    if session is not None:
        session._cold_archive_ref = marker


def repair_pending_hot_cleanup(session_id: str) -> None:
    """Finish a crash-interrupted post-commit cleanup from metadata load."""
    with session_storage_lock(session_id):
        marker = _hot_cold_marker(session_id)
        if not marker or marker.get("cleanup_complete") is True:
            return
        _verify_package(session_id)
        _clean_hot_artifacts(session_id)
        _mark_hot_cleanup_complete(session_id)


def _clean_hot_artifacts(session_id: str) -> None:
    models = _models()
    backup_path = models.SESSION_DIR / f"{session_id}.json.bak"
    attachment_path = _attachment_dir(session_id)
    try:
        backup_path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Failed to remove hot sidecar backup for archived session %s", session_id, exc_info=True)
    shutil.rmtree(attachment_path, ignore_errors=True)
    try:
        from api.turn_journal import TURN_JOURNAL_DIR_NAME, delete_turn_journal

        delete_turn_journal(session_id, session_dir=models.SESSION_DIR)
    except Exception:
        logger.warning("Failed to remove hot turn journal for archived session %s", session_id, exc_info=True)
        TURN_JOURNAL_DIR_NAME = "_turn_journal"
    try:
        from api.run_journal import RUN_JOURNAL_DIR_NAME, delete_run_journal

        delete_run_journal(session_id, session_dir=models.SESSION_DIR)
    except Exception:
        logger.warning("Failed to remove hot run journal for archived session %s", session_id, exc_info=True)
        RUN_JOURNAL_DIR_NAME = "_run_journal"

    turn_dir = models.SESSION_DIR / TURN_JOURNAL_DIR_NAME
    leftovers = []
    if backup_path.exists():
        leftovers.append("sidecar backup")
    if attachment_path.exists():
        leftovers.append("attachments")
    if (models.SESSION_DIR / RUN_JOURNAL_DIR_NAME / session_id).exists():
        leftovers.append("run journal")
    if (turn_dir / f"{session_id}.jsonl").exists() or any(turn_dir.glob(f"{session_id}~*.jsonl")):
        leftovers.append("turn journal")
    if leftovers:
        raise ColdArchiveError(
            f"Cold archive committed but hot cleanup is incomplete for {session_id}: "
            + ", ".join(leftovers)
        )


def cold_archive_session(session) -> bool:
    with session_storage_lock(session.session_id):
        return _cold_archive_session_locked(session)


def _cold_archive_session_locked(session) -> bool:
    """Cold-archive a settled native WebUI session.

    Returns ``True`` for a cold transition. Imported/external sessions retain
    the legacy metadata-only archive behavior and return ``False``.
    """
    if getattr(session, "_cold_archived", False):
        _verify_package(session.session_id)
        _clean_hot_artifacts(session.session_id)
        _mark_hot_cleanup_complete(session.session_id, session=session)
        _LIVE_GENERATIONS.pop(session.session_id, None)
        _models()._write_session_index(updates=[session])
        return True
    if not _native_webui_session(session):
        session.archived = True
        session.save(touch_updated_at=False)
        return False
    models = _models()
    hot_path = session.path
    if not hot_path.is_file():
        # A brand-new empty session can exist in the in-memory registry before
        # its first sidecar write. Publish that exact empty session first so
        # Archive remains a valid lifecycle action and the cold package still
        # has a durable source payload.
        session.save(touch_updated_at=False)
    if not hot_path.is_file():
        raise ColdArchiveError(f"Hot session {session.session_id} is missing")

    # The route resolves its object before acquiring this storage lock. Another
    # settled writer may have committed a newer full sidecar in that interval,
    # or the process cache itself may be older than disk. Refresh the existing
    # object in place so both the cold payload and the caller's cached reference
    # use the latest durable transcript. Archive never publishes an older
    # in-memory snapshot over newer on-disk messages.
    durable = models.Session.load(session.session_id)
    if durable is None:
        raise ColdArchiveError(f"Hot session {session.session_id} is unreadable")
    if durable is not session:
        session.__dict__.update(durable.__dict__)
    if getattr(session, "_cold_archived", False):
        _verify_package(session.session_id)
        _clean_hot_artifacts(session.session_id)
        _mark_hot_cleanup_complete(session.session_id, session=session)
        _LIVE_GENERATIONS.pop(session.session_id, None)
        models._write_session_index(updates=[session])
        return True
    if not _native_webui_session(session):
        session.archived = True
        session.save(touch_updated_at=False)
        return False
    _assert_settled(session)

    final = cold_archive_package_path(session.session_id)
    if final.exists():
        # Resolve an interrupted transition under the same storage lock. A hot
        # stub means the verified package is already canonical; a full live
        # sidecar means the package is only an uncommitted/stale duplicate.
        try:
            hot_payload = json.loads(hot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            hot_payload = {}
        hot_marker = hot_payload.get("cold_archive")
        if isinstance(hot_marker, dict):
            _package, manifest = _verify_package(session.session_id)
            session.archived = True
            session.cold_archive_generation = manifest["generation"]
            session._cold_archive_ref = hot_marker
            session._cold_archived = True
            session._metadata_message_count = int(hot_payload.get("message_count") or 0)
            _clean_hot_artifacts(session.session_id)
            _mark_hot_cleanup_complete(session.session_id, session=session)
            _LIVE_GENERATIONS.pop(session.session_id, None)
            models._write_session_index(updates=[session])
            return True
        if hot_payload.get("archived") is False:
            _verify_package(session.session_id)
            preserved_backup = final / _SOURCE_BACKUP_NAME
            hot_backup = hot_path.with_suffix(".json.bak")
            if preserved_backup.is_file() and not hot_backup.exists():
                _copy_file_durable(preserved_backup, hot_backup)
            shutil.rmtree(final)
            _fsync_dir(final.parent)
        else:
            raise ColdArchiveError(f"Cold archive for {session.session_id} already exists")

    attachment_source = _attachment_dir(session.session_id)
    source_backup = hot_path.with_suffix(".json.bak")
    required = (
        hot_path.stat().st_size
        + _tree_size(source_backup)
        + _tree_size(attachment_source)
        + 1024 * 1024
    )
    root = cold_archive_root()
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < required:
        raise ColdArchiveError("Not enough free space to stage the cold archive safely")

    generation = uuid.uuid4().hex
    payload = session._persistence_dict()
    payload["archived"] = True
    payload["cold_archive_generation"] = generation
    stage = root / f".{session.session_id}.tmp.{uuid.uuid4().hex}"
    try:
        stage.mkdir(mode=0o700)
        _atomic_write_json(stage / _SESSION_NAME, payload)
        source_backup = hot_path.with_suffix(".json.bak")
        if source_backup.is_file():
            _copy_file_durable(source_backup, stage / _SOURCE_BACKUP_NAME)
        if attachment_source.is_dir():
            _assert_tree_has_no_symlinks(attachment_source)
            _copy_tree(attachment_source, stage / "attachments")
        manifest = _write_manifest(
            stage,
            session.session_id,
            generation=generation,
        )
        _verify_staged = manifest.get("files", {})
        if _SESSION_NAME not in _verify_staged:
            raise ColdArchiveError("Cold archive staging manifest is incomplete")
        _fsync_dir(stage)
        os.replace(stage, final)
        _fsync_dir(root)
        try:
            _verify_package(session.session_id)
            # Once the verified package is durable it supersedes the ordinary
            # hot-sidecar shrink backup. Remove that backup before publishing
            # the empty-message stub so startup recovery cannot mistake the
            # intentional cold transition for accidental data loss.
            source_backup.unlink(missing_ok=True)
            _fsync_dir(source_backup.parent)
            _write_stub(session, payload, manifest)
        except Exception:
            # os.replace() can commit the stub before a following directory
            # fsync reports an error. Never delete the verified package after
            # stub publication has begun: the hot file may already reference it.
            # A retry resolves either full-hot+duplicate-cold or
            # stub-hot+canonical-cold state under the storage lock.
            raise
        _clean_hot_artifacts(session.session_id)
        _mark_hot_cleanup_complete(session.session_id, session=session)
        _LIVE_GENERATIONS.pop(session.session_id, None)
        models._write_session_index(updates=[session])
        return True
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def load_cold_archived_session(session_id: str, *, stub: dict | None = None):
    with session_storage_lock(session_id):
        marker = _hot_cold_marker(session_id)
        if marker is None:
            # The caller may have read a cold stub immediately before an
            # unarchive committed. Re-resolve the now-live sidecar rather than
            # failing against the intentionally removed package.
            return _models().Session.load(session_id)
        if marker.get("cleanup_complete") is not True:
            _verify_package(session_id)
            _clean_hot_artifacts(session_id)
            _mark_hot_cleanup_complete(session_id)
            marker = _hot_cold_marker(session_id) or marker
        return _load_cold_archived_session_locked(
            session_id,
            stub={**(stub or {}), "cold_archive": marker},
        )


def _load_cold_archived_session_locked(session_id: str, *, stub: dict | None = None):
    package, manifest = _verify_package(session_id)
    try:
        payload = json.loads((package / _SESSION_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ColdArchiveError(f"Cold archive transcript for {session_id} is unreadable") from exc
    if payload.get("session_id") != session_id or not payload.get("archived"):
        raise ColdArchiveError(f"Cold archive transcript for {session_id} is inconsistent")
    session = _models().Session(**payload)
    marker = (stub or {}).get("cold_archive")
    if not isinstance(marker, dict):
        marker = {"version": ARCHIVE_SCHEMA, "message_count": len(session.messages or [])}
    marker = dict(marker)
    marker["generation"] = manifest["generation"]
    session.cold_archive_generation = manifest["generation"]
    session._cold_archive_ref = marker
    session._cold_archived = True
    session._metadata_message_count = len(session.messages or [])
    return session


def update_cold_archived_session(session, *, touch_updated_at: bool = True) -> None:
    """Persist metadata/content changes without rehydrating the hot sidecar."""
    package, manifest = _verify_package(session.session_id)
    expected_generation = manifest["generation"]
    if getattr(session, "cold_archive_generation", None) != expected_generation:
        raise ColdArchiveError(
            f"Refusing stale cold-archive update for {session.session_id}"
        )
    next_generation = uuid.uuid4().hex
    if touch_updated_at:
        session.updated_at = time.time()
    session.archived = True
    payload = session._persistence_dict()
    payload["archived"] = True
    payload["cold_archive_generation"] = next_generation
    session_path = package / _SESSION_NAME
    previous = package / _PREVIOUS_SESSION_NAME
    _atomic_write_bytes(previous, session_path.read_bytes())
    try:
        _atomic_write_json(session_path, payload)
        manifest = _write_manifest(
            package,
            session.session_id,
            created_at=float(manifest.get("created_at") or time.time()),
            generation=next_generation,
        )
        _write_stub(session, payload, manifest)
        previous.unlink(missing_ok=True)
    except Exception:
        # Leave previous in place. Verification will roll the package back to
        # the manifest-referenced generation on the next load.
        raise


def restore_cold_archived_session(session):
    with session_storage_lock(session.session_id):
        return _restore_cold_archived_session_locked(session)


def _restore_cold_archived_session_locked(session):
    """Rehydrate a cold native session and remove its package after verification."""
    if not getattr(session, "_cold_archived", False):
        session.archived = False
        session.save(touch_updated_at=False)
        package = cold_archive_package_path(session.session_id)
        if package.is_dir() and _hot_cold_marker(session.session_id) is None:
            _verify_package(session.session_id)
            shutil.rmtree(package)
            try:
                _fsync_dir(package.parent)
            except OSError:
                logger.warning("Failed to fsync restored cold root for %s", session.session_id, exc_info=True)
        return session
    _assert_settled(session)
    package, manifest = _verify_package(session.session_id)
    payload = json.loads((package / _SESSION_NAME).read_text(encoding="utf-8"))
    payload["archived"] = False
    payload.pop("cold_archive", None)

    attachment_source = package / "attachments"
    attachment_target = _attachment_dir(session.session_id)
    staged_attachment = attachment_target.with_name(
        f".{attachment_target.name}.restore.{uuid.uuid4().hex}"
    )
    published_attachment = False
    try:
        if attachment_source.is_dir():
            if attachment_target.exists():
                if any(attachment_target.iterdir()):
                    if not _trees_match(attachment_source, attachment_target):
                        raise ColdArchiveError("Live attachment directory is not empty; refusing overwrite")
                    # A prior process may have died after atomically publishing
                    # this exact verified tree but before committing the hot
                    # sidecar. Treat the matching tree as a retryable stage.
                    published_attachment = True
                else:
                    attachment_target.rmdir()
            if not published_attachment:
                attachment_target.parent.mkdir(parents=True, exist_ok=True)
                _copy_tree(attachment_source, staged_attachment)
                os.replace(staged_attachment, attachment_target)
                published_attachment = True
                _fsync_dir(attachment_target.parent)

        # The verified cold package remains the rollback source until the live
        # sidecar is fully committed. A hot .bak would make startup recovery
        # misclassify the intentional stub as a truncated live transcript.
        hot_backup = session.path.with_suffix(".json.bak")
        hot_backup.unlink(missing_ok=True)
        _fsync_dir(hot_backup.parent)
        _atomic_write_json(session.path, payload)
        persisted = json.loads(session.path.read_text(encoding="utf-8"))
        if persisted.get("session_id") != session.session_id or persisted.get("archived"):
            raise ColdArchiveError("Restored hot session failed verification")

        session.archived = False
        session.cold_archive_generation = manifest["generation"]
        session._cold_archive_ref = None
        session._cold_archived = False
        session._metadata_message_count = len(session.messages or [])
        _LIVE_GENERATIONS[session.session_id] = manifest["generation"]
        shutil.rmtree(package)
        try:
            _fsync_dir(package.parent)
        except OSError:
            logger.warning("Failed to fsync restored cold root for %s", session.session_id, exc_info=True)
        try:
            _models()._write_session_index(updates=[session])
        except Exception:
            logger.warning("Failed to refresh restored session index for %s", session.session_id, exc_info=True)
        return session
    except Exception:
        shutil.rmtree(staged_attachment, ignore_errors=True)
        if published_attachment:
            try:
                hot_payload = json.loads(session.path.read_text(encoding="utf-8"))
            except Exception:
                hot_payload = {}
            if isinstance(hot_payload.get("cold_archive"), dict):
                # The hot stub is still authoritative, so roll back the copied
                # attachment tree and leave the verified package retryable.
                shutil.rmtree(attachment_target, ignore_errors=True)
        raise


def delete_cold_archive_artifacts(session_id: str) -> None:
    """Quarantine then delete a cold package under the session storage lock."""
    with session_storage_lock(session_id):
        root = cold_archive_root()
        root.mkdir(parents=True, exist_ok=True)
        package = cold_archive_package_path(session_id)
        if package.exists():
            quarantine = root / f".deleted-{session_id}-{uuid.uuid4().hex}"
            os.replace(package, quarantine)
            _fsync_dir(root)
        quarantines = list(root.glob(f".deleted-{session_id}-*"))
        for quarantine in quarantines:
            shutil.rmtree(quarantine)
        if package.exists() or any(root.glob(f".deleted-{session_id}-*")):
            raise ColdArchiveError(f"Cold archive deletion is incomplete for {session_id}")
        _fsync_dir(root)
        _LIVE_GENERATIONS.pop(session_id, None)
