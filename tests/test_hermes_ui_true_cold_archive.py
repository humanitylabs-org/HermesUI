from __future__ import annotations

import json
import os
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import api.config as config
import api.models as models
import api.session_cold_archive as cold
import api.upload as upload
from tests._pytest_port import BASE as TEST_BASE


@pytest.fixture
def isolated_session_store(tmp_path, monkeypatch):
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    monkeypatch.setattr(models, "SESSION_DIR", session_dir)
    monkeypatch.setattr(models, "SESSION_INDEX_FILE", session_dir / "_index.json")
    monkeypatch.setattr(upload, "STATE_DIR", tmp_path)
    cold._LIVE_GENERATIONS.clear()
    with models.LOCK:
        models.SESSIONS.clear()
    with config.ACTIVE_RUNS_LOCK:
        config.ACTIVE_RUNS.clear()
    with config.SESSION_WRITEBACK_OWNERS_LOCK:
        config.SESSION_WRITEBACK_OWNERS.clear()
    yield tmp_path, session_dir
    with models.LOCK:
        models.SESSIONS.clear()
    with config.ACTIVE_RUNS_LOCK:
        config.ACTIVE_RUNS.clear()
    with config.SESSION_WRITEBACK_OWNERS_LOCK:
        config.SESSION_WRITEBACK_OWNERS.clear()
    cold._LIVE_GENERATIONS.clear()


def _session(sid: str = "cold_native") -> models.Session:
    return models.Session(
        session_id=sid,
        title="A session with a large transcript",
        workspace="/tmp",
        profile="default",
        messages=[
            {"role": "user", "content": "hello " * 200, "timestamp": 1.0},
            {"role": "assistant", "content": "world " * 200, "timestamp": 2.0},
        ],
        context_messages=[{"role": "user", "content": "context " * 100}],
        tool_calls=[{"id": "call_1", "name": "demo", "arguments": {"text": "x" * 500}}],
        anchor_activity_scenes={"scene": {"updated_at": 3.0, "body": "y" * 500}},
        worktree_path="/tmp/retained-worktree",
        worktree_branch="feature/test",
    )


def _write_hot_artifacts(tmp_path: Path, session_dir: Path, sid: str) -> Path:
    attachment_dir = tmp_path / "attachments" / sid
    attachment_dir.mkdir(parents=True)
    (attachment_dir / "proof.txt").write_text("attachment payload", encoding="utf-8")
    run_dir = session_dir / "_run_journal" / sid
    run_dir.mkdir(parents=True)
    (run_dir / "run.jsonl").write_text('{"event":"provider"}\n', encoding="utf-8")
    turn_dir = session_dir / "_turn_journal"
    turn_dir.mkdir(parents=True)
    (turn_dir / f"{sid}~123.jsonl").write_text('{"event":"user"}\n', encoding="utf-8")
    return attachment_dir


def _post(path: str, body: dict) -> tuple[dict, int]:
    request = urllib.request.Request(
        TEST_BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read()), response.status
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read()), exc.code


def _get(path: str) -> tuple[dict, int]:
    try:
        with urllib.request.urlopen(TEST_BASE + path, timeout=20) as response:
            return json.loads(response.read()), response.status
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read()), exc.code


def test_native_archive_commits_verified_package_and_tiny_hot_stub_then_restores(
    isolated_session_store,
):
    tmp_path, session_dir = isolated_session_store
    session = _session()
    session.save(touch_updated_at=False)
    hot_path = session.path
    hot_backup = hot_path.with_suffix(".json.bak")
    shutil.copy2(hot_path, hot_backup)
    attachment_dir = _write_hot_artifacts(tmp_path, session_dir, session.session_id)
    original_size = hot_path.stat().st_size

    assert cold.cold_archive_session(session) is True

    package = cold.cold_archive_package_path(session.session_id)
    stub = json.loads(hot_path.read_text(encoding="utf-8"))
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    archived_payload = json.loads((package / "session.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == 1
    assert manifest["session_id"] == session.session_id
    assert manifest["journals"] == "discarded_after_commit"
    assert stub["archived"] is True
    assert stub["cold_archive"]["version"] == 1
    assert stub["message_count"] == 2
    assert stub["messages"] == []
    assert "tool_calls" not in stub
    assert "context_messages" not in stub
    assert "anchor_activity_scenes" not in stub
    assert hot_path.stat().st_size < original_size / 2
    assert archived_payload["messages"] == session.messages
    assert archived_payload["context_messages"] == session.context_messages
    assert archived_payload["tool_calls"] == session.tool_calls
    assert archived_payload["worktree_path"] == "/tmp/retained-worktree"
    assert (package / "attachments" / "proof.txt").read_text(encoding="utf-8") == "attachment payload"
    assert (package / "source-backup.json").exists()
    assert not hot_backup.exists()
    assert not attachment_dir.exists()
    assert not (session_dir / "_run_journal" / session.session_id).exists()
    assert not list((session_dir / "_turn_journal").glob(f"{session.session_id}*"))

    # Sidebar metadata stays cheap and does not hydrate the transcript.
    metadata = models.Session.load_metadata_only(session.session_id)
    assert metadata is not None
    assert metadata.archived is True
    assert metadata._metadata_message_count == 2
    assert metadata.messages == []
    assert metadata._loaded_metadata_only is True

    # Opening reads the verified cold transcript without rewriting the hot stub.
    stub_before_open = hot_path.read_bytes()
    loaded = models.Session.load(session.session_id)
    assert loaded is not None
    assert loaded.messages == session.messages
    assert loaded.tool_calls == session.tool_calls
    assert loaded._cold_archived is True
    assert hot_path.read_bytes() == stub_before_open

    cold.restore_cold_archived_session(loaded)
    restored = json.loads(hot_path.read_text(encoding="utf-8"))
    assert restored["archived"] is False
    assert restored["messages"] == session.messages
    assert "cold_archive" not in restored
    assert attachment_dir.joinpath("proof.txt").read_text(encoding="utf-8") == "attachment payload"
    assert not package.exists()
    # The verified cold package is the rollback source until the complete live
    # sidecar commits; a shrink-recovery backup would be unsafe here.
    assert not hot_backup.exists()
    assert loaded._cold_archived is False
    # Recovery journals are deliberately not reactivated during restore.
    assert not (session_dir / "_run_journal" / session.session_id).exists()
    assert not list((session_dir / "_turn_journal").glob(f"{session.session_id}*"))


def test_full_load_then_save_keeps_archived_transcript_cold(isolated_session_store):
    _tmp_path, _session_dir = isolated_session_store
    session = _session("cold_save")
    session.save(touch_updated_at=False)
    cold.cold_archive_session(session)

    loaded = models.Session.load(session.session_id)
    assert loaded is not None
    loaded.title = "Renamed while archived"
    loaded.save(touch_updated_at=False)

    stub = json.loads(loaded.path.read_text(encoding="utf-8"))
    payload = json.loads(
        (cold.cold_archive_package_path(session.session_id) / "session.json").read_text(encoding="utf-8")
    )
    assert stub["title"] == "Renamed while archived"
    assert stub["messages"] == []
    assert payload["title"] == "Renamed while archived"
    assert payload["messages"] == session.messages
    assert loaded.path.stat().st_size < (cold.cold_archive_package_path(session.session_id) / "session.json").stat().st_size


def test_archive_refuses_persisted_and_runtime_active_sessions(isolated_session_store):
    _tmp_path, _session_dir = isolated_session_store
    pending = _session("cold_pending")
    pending.pending_user_message = "still running"
    pending.save(touch_updated_at=False)
    before = pending.path.read_bytes()
    with pytest.raises(cold.ActiveSessionArchiveError):
        cold.cold_archive_session(pending)
    assert pending.path.read_bytes() == before
    assert not cold.cold_archive_package_path(pending.session_id).exists()

    runtime = _session("cold_runtime")
    runtime.save(touch_updated_at=False)
    with config.ACTIVE_RUNS_LOCK:
        config.ACTIVE_RUNS["stream-1"] = {"session_id": runtime.session_id, "phase": "running"}
    with pytest.raises(cold.ActiveSessionArchiveError, match="worker"):
        cold.cold_archive_session(runtime)
    assert not cold.cold_archive_package_path(runtime.session_id).exists()

    with config.ACTIVE_RUNS_LOCK:
        config.ACTIVE_RUNS.clear()
    config.register_session_writeback_owner(runtime.session_id, "stream-2")
    with pytest.raises(cold.ActiveSessionArchiveError, match="writeback"):
        cold.cold_archive_session(runtime)


def test_imported_session_keeps_legacy_flag_only_archive_behavior(isolated_session_store):
    _tmp_path, _session_dir = isolated_session_store
    session = _session("cold_imported")
    session.is_cli_session = True
    session.source_tag = "cli"
    session.save(touch_updated_at=False)

    assert cold.cold_archive_session(session) is False
    archived_payload = json.loads(session.path.read_text(encoding="utf-8"))
    assert archived_payload["archived"] is True
    assert archived_payload["messages"] == session.messages
    assert "cold_archive" not in archived_payload
    assert not cold.cold_archive_package_path(session.session_id).exists()

    cold.restore_cold_archived_session(session)
    restored_payload = json.loads(session.path.read_text(encoding="utf-8"))
    assert restored_payload["archived"] is False
    assert restored_payload["messages"] == session.messages


def test_stub_failure_keeps_both_verified_cold_copy_and_hot_authority(
    isolated_session_store, monkeypatch
):
    tmp_path, session_dir = isolated_session_store
    session = _session("cold_rollback")
    session.save(touch_updated_at=False)
    attachment_dir = _write_hot_artifacts(tmp_path, session_dir, session.session_id)
    before = session.path.read_bytes()

    def fail_stub(*_args, **_kwargs):
        raise OSError("injected stub failure")

    monkeypatch.setattr(cold, "_write_stub", fail_stub)
    with pytest.raises(OSError, match="injected"):
        cold.cold_archive_session(session)

    assert session.path.read_bytes() == before
    assert attachment_dir.joinpath("proof.txt").exists()
    assert (session_dir / "_run_journal" / session.session_id / "run.jsonl").exists()
    assert list((session_dir / "_turn_journal").glob(f"{session.session_id}*"))
    package = cold.cold_archive_package_path(session.session_id)
    assert package.exists()
    cold._verify_package(session.session_id)
    assert session.archived is False


def test_stub_failure_retry_preserves_recovery_only_source_backup(
    isolated_session_store, monkeypatch
):
    _tmp_path, _session_dir = isolated_session_store
    session = _session("archive_stub_retry_backup")
    session.save(touch_updated_at=False)
    backup = session.path.with_suffix(".json.bak")
    backup_payload = json.loads(session.path.read_text(encoding="utf-8"))
    backup_payload["messages"].append(
        {"role": "assistant", "content": "recovery-only tail"}
    )
    backup.write_text(json.dumps(backup_payload), encoding="utf-8")
    original_write_stub = cold._write_stub

    def fail_stub(*_args, **_kwargs):
        raise OSError("injected stub failure with backup")

    monkeypatch.setattr(cold, "_write_stub", fail_stub)
    with pytest.raises(OSError, match="stub failure with backup"):
        cold.cold_archive_session(session)

    package = cold.cold_archive_package_path(session.session_id)
    assert package.joinpath("source-backup.json").is_file()
    assert not backup.exists()

    monkeypatch.setattr(cold, "_write_stub", original_write_stub)
    cold.cold_archive_session(session)
    restored_backup = json.loads(
        package.joinpath("source-backup.json").read_text(encoding="utf-8")
    )
    assert restored_backup["messages"][-1]["content"] == "recovery-only tail"


def test_restored_session_remains_saveable_after_reload(isolated_session_store):
    _tmp_path, _session_dir = isolated_session_store
    session = _session("restored_reload_save")
    session.save(touch_updated_at=False)
    cold.cold_archive_session(session)
    archived = models.Session.load(session.session_id)
    assert archived is not None
    cold.restore_cold_archived_session(archived)

    with models.LOCK:
        models.SESSIONS.pop(session.session_id, None)
    reloaded = models.Session.load(session.session_id)
    assert reloaded is not None
    assert reloaded.cold_archive_generation
    reloaded.title = "Saved after restore"
    reloaded.save(touch_updated_at=False)
    saved = models.Session.load(session.session_id)
    assert saved is not None
    assert saved.title == "Saved after restore"


def test_directory_fsync_error_after_stub_replace_never_deletes_cold_payload(
    isolated_session_store, monkeypatch
):
    _tmp_path, _session_dir = isolated_session_store
    session = _session("cold_post_replace_fsync")
    session.save(touch_updated_at=False)
    original_fsync_dir = cold._fsync_dir
    injected = False

    def fail_after_stub_replace(path):
        nonlocal injected
        if path == session.path.parent and session.path.is_file():
            payload = json.loads(session.path.read_text(encoding="utf-8"))
            if isinstance(payload.get("cold_archive"), dict) and not injected:
                injected = True
                raise OSError("injected post-replace fsync failure")
        return original_fsync_dir(path)

    monkeypatch.setattr(cold, "_fsync_dir", fail_after_stub_replace)
    with pytest.raises(OSError, match="post-replace"):
        cold.cold_archive_session(session)

    package = cold.cold_archive_package_path(session.session_id)
    assert package.exists()
    cold._verify_package(session.session_id)
    loaded = models.Session.load(session.session_id)
    assert loaded is not None
    assert loaded.messages == session.messages


def test_hot_cleanup_failure_is_repaired_by_metadata_startup_load(
    isolated_session_store, monkeypatch
):
    tmp_path, session_dir = isolated_session_store
    session = _session("cold_cleanup_retry")
    session.save(touch_updated_at=False)
    attachment_dir = _write_hot_artifacts(tmp_path, session_dir, session.session_id)
    original_rmtree = cold.shutil.rmtree

    def leave_hot_attachment_tree(path, *args, **kwargs):
        if Path(path) == attachment_dir:
            return None
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(cold.shutil, "rmtree", leave_hot_attachment_tree)
    with pytest.raises(cold.ColdArchiveError, match="hot cleanup is incomplete"):
        cold.cold_archive_session(session)

    package = cold.cold_archive_package_path(session.session_id)
    assert package.exists()
    assert attachment_dir.exists()
    assert isinstance(json.loads(session.path.read_text(encoding="utf-8")).get("cold_archive"), dict)

    monkeypatch.setattr(cold.shutil, "rmtree", original_rmtree)
    metadata = models.Session.load_metadata_only(session.session_id)
    assert metadata is not None
    assert metadata._cold_archive_ref["cleanup_complete"] is True
    assert package.exists()
    assert not attachment_dir.exists()


def test_late_save_waits_for_archive_and_is_rejected_as_stale(
    isolated_session_store, monkeypatch
):
    _tmp_path, _session_dir = isolated_session_store
    session = _session("cold_concurrent_save")
    session.save(touch_updated_at=False)
    stale = models.Session.load(session.session_id)
    assert stale is not None

    entered = threading.Event()
    release = threading.Event()
    archive_errors = []
    save_errors = []
    original_write_stub = cold._write_stub

    def blocked_write_stub(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original_write_stub(*args, **kwargs)

    monkeypatch.setattr(cold, "_write_stub", blocked_write_stub)

    def archive_worker():
        try:
            cold.cold_archive_session(session)
        except Exception as exc:  # pragma: no cover - assertion reports detail
            archive_errors.append(exc)

    def late_save_worker():
        try:
            stale.title = "Late stale title"
            stale.save(touch_updated_at=False)
        except Exception as exc:
            save_errors.append(exc)

    archive_thread = threading.Thread(target=archive_worker)
    archive_thread.start()
    assert entered.wait(timeout=5)
    save_thread = threading.Thread(target=late_save_worker)
    save_thread.start()
    release.set()
    archive_thread.join(timeout=5)
    save_thread.join(timeout=5)

    assert not archive_errors
    assert len(save_errors) == 1
    assert isinstance(save_errors[0], cold.ColdArchiveError)
    loaded = models.Session.load(session.session_id)
    assert loaded is not None
    assert loaded.title != "Late stale title"
    assert loaded.messages == session.messages


def test_archive_refreshes_stale_live_object_from_durable_sidecar(
    isolated_session_store,
):
    _tmp_path, _session_dir = isolated_session_store
    durable = _session("cold_archive_stale_live")
    durable.save(touch_updated_at=False)
    stale = _session("cold_archive_stale_live")
    stale.messages = stale.messages[:1]
    stale.context_messages = stale.context_messages[:1]

    cold.cold_archive_session(stale)

    archived = models.Session.load(stale.session_id)
    assert archived is not None
    assert archived.messages == durable.messages
    assert len(archived.messages) == 2
    assert stale.messages == durable.messages


def test_cold_reader_waits_for_manifest_commit_and_sees_one_generation(
    isolated_session_store, monkeypatch
):
    _tmp_path, _session_dir = isolated_session_store
    session = _session("cold_reader_writer")
    session.save(touch_updated_at=False)
    cold.cold_archive_session(session)
    writer_session = models.Session.load(session.session_id)
    assert writer_session is not None
    writer_session.title = "Committed title"

    package = cold.cold_archive_package_path(session.session_id)
    entered = threading.Event()
    release = threading.Event()
    writer_errors = []
    reader_errors = []
    reader_results = []
    original_atomic_write_json = cold._atomic_write_json

    def block_after_transcript_replace(path, payload):
        result = original_atomic_write_json(path, payload)
        if path == package / "session.json" and payload.get("title") == "Committed title":
            entered.set()
            assert release.wait(timeout=5)
        return result

    monkeypatch.setattr(cold, "_atomic_write_json", block_after_transcript_replace)

    def writer():
        try:
            writer_session.save(touch_updated_at=False)
        except Exception as exc:  # pragma: no cover - assertion reports detail
            writer_errors.append(exc)

    def reader():
        try:
            reader_results.append(models.Session.load(session.session_id))
        except Exception as exc:  # pragma: no cover - assertion reports detail
            reader_errors.append(exc)

    writer_thread = threading.Thread(target=writer)
    writer_thread.start()
    assert entered.wait(timeout=5)
    reader_thread = threading.Thread(target=reader)
    reader_thread.start()
    release.set()
    writer_thread.join(timeout=5)
    reader_thread.join(timeout=5)

    assert not writer_thread.is_alive()
    assert not reader_thread.is_alive()
    assert not writer_errors
    assert not reader_errors
    assert len(reader_results) == 1
    assert reader_results[0] is not None
    assert reader_results[0].title == "Committed title"
    assert reader_results[0].messages == session.messages


def test_upload_publication_waits_for_archive_and_refuses_archived_target(
    isolated_session_store, monkeypatch
):
    tmp_path, session_dir = isolated_session_store
    session = _session("cold_upload_race")
    session.save(touch_updated_at=False)
    attachment_dir = _write_hot_artifacts(tmp_path, session_dir, session.session_id)

    entered = threading.Event()
    release = threading.Event()
    archive_errors = []
    upload_errors = []
    upload_rejected = []
    original_copy_tree = cold._copy_tree

    def block_after_attachment_snapshot(source, destination):
        result = original_copy_tree(source, destination)
        if source == attachment_dir:
            entered.set()
            assert release.wait(timeout=5)
        return result

    monkeypatch.setattr(cold, "_copy_tree", block_after_attachment_snapshot)

    def archive_worker():
        try:
            cold.cold_archive_session(session)
        except Exception as exc:  # pragma: no cover - assertion reports detail
            archive_errors.append(exc)

    def upload_worker():
        try:
            with cold.session_storage_lock(session.session_id):
                target = models.Session.load(session.session_id)
                if target is None or target.archived:
                    upload_rejected.append(True)
                    return
                upload._atomic_upload_write(
                    upload._upload_destination(session.session_id, "late.txt"),
                    b"late upload",
                )
        except Exception as exc:  # pragma: no cover - assertion reports detail
            upload_errors.append(exc)

    archive_thread = threading.Thread(target=archive_worker)
    archive_thread.start()
    assert entered.wait(timeout=5)
    upload_thread = threading.Thread(target=upload_worker)
    upload_thread.start()
    release.set()
    archive_thread.join(timeout=5)
    upload_thread.join(timeout=5)

    assert not archive_thread.is_alive()
    assert not upload_thread.is_alive()
    assert not archive_errors
    assert not upload_errors
    assert upload_rejected == [True]
    package = cold.cold_archive_package_path(session.session_id)
    assert not (package / "attachments" / "late.txt").exists()
    assert not (attachment_dir / "late.txt").exists()


def test_interrupted_cold_metadata_update_rolls_back_to_manifest_generation(
    isolated_session_store, monkeypatch
):
    _tmp_path, _session_dir = isolated_session_store
    session = _session("cold_update_rollback")
    session.save(touch_updated_at=False)
    cold.cold_archive_session(session)
    loaded = models.Session.load(session.session_id)
    assert loaded is not None
    loaded.title = "Uncommitted rename"

    original_write_manifest = cold._write_manifest

    def fail_manifest(*_args, **_kwargs):
        raise OSError("injected manifest failure")

    monkeypatch.setattr(cold, "_write_manifest", fail_manifest)
    with pytest.raises(OSError, match="manifest"):
        loaded.save(touch_updated_at=False)
    monkeypatch.setattr(cold, "_write_manifest", original_write_manifest)

    # The old manifest still points to the previous generation. Full load
    # restores that exact generation rather than accepting unverified bytes.
    recovered = models.Session.load(session.session_id)
    assert recovered is not None
    assert recovered.title == "A session with a large transcript"
    assert recovered.messages == session.messages


def test_stale_cold_metadata_update_is_rejected_without_reverting_newer_state(
    isolated_session_store,
):
    _tmp_path, _session_dir = isolated_session_store
    session = _session("cold_update_cas")
    session.save(touch_updated_at=False)
    cold.cold_archive_session(session)

    first = models.Session.load(session.session_id)
    stale = models.Session.load(session.session_id)
    assert first is not None and stale is not None
    first.title = "Committed title"
    first.save(touch_updated_at=False)

    stale.model = "stale-model-change"
    with pytest.raises(cold.ColdArchiveError, match="stale (save|cold-archive update)"):
        stale.save(touch_updated_at=False)

    committed = models.Session.load(session.session_id)
    assert committed is not None
    assert committed.title == "Committed title"
    assert committed.model != "stale-model-change"
    assert committed.messages == session.messages


def test_archive_cleanup_crash_cannot_trigger_startup_backup_rehydration(
    isolated_session_store, monkeypatch
):
    _tmp_path, _session_dir = isolated_session_store
    session = _session("cold_archive_recovery_guard")
    session.save(touch_updated_at=False)
    hot_backup = session.path.with_suffix(".json.bak")
    shutil.copyfile(session.path, hot_backup)

    def die_after_stub(_session_id):
        raise OSError("injected post-stub cleanup crash")

    monkeypatch.setattr(cold, "_clean_hot_artifacts", die_after_stub)
    with pytest.raises(OSError, match="post-stub cleanup"):
        cold.cold_archive_session(session)

    stub_before = json.loads(session.path.read_text(encoding="utf-8"))
    assert isinstance(stub_before.get("cold_archive"), dict)
    assert stub_before["messages"] == []
    assert not hot_backup.exists()

    from api.session_recovery import recover_session

    recovery = recover_session(session.path)
    assert recovery["restored"] is False
    stub_after = json.loads(session.path.read_text(encoding="utf-8"))
    assert isinstance(stub_after.get("cold_archive"), dict)
    assert stub_after["messages"] == []


def test_restore_sidecar_failure_removes_copied_hot_attachments_and_stays_retryable(
    isolated_session_store, monkeypatch
):
    tmp_path, session_dir = isolated_session_store
    session = _session("cold_restore_rollback")
    session.save(touch_updated_at=False)
    attachment_dir = _write_hot_artifacts(tmp_path, session_dir, session.session_id)
    cold.cold_archive_session(session)
    loaded = models.Session.load(session.session_id)
    assert loaded is not None
    original_atomic_write_json = cold._atomic_write_json

    def fail_hot_sidecar(path, payload):
        if path == loaded.path:
            raise OSError("injected restore sidecar failure")
        return original_atomic_write_json(path, payload)

    monkeypatch.setattr(cold, "_atomic_write_json", fail_hot_sidecar)
    with pytest.raises(OSError, match="restore sidecar"):
        cold.restore_cold_archived_session(loaded)

    assert not attachment_dir.exists()
    assert cold.cold_archive_package_path(session.session_id).exists()
    stub = json.loads(loaded.path.read_text(encoding="utf-8"))
    assert stub["archived"] is True
    assert isinstance(stub["cold_archive"], dict)

    monkeypatch.setattr(cold, "_atomic_write_json", original_atomic_write_json)
    retried = models.Session.load(session.session_id)
    cold.restore_cold_archived_session(retried)
    assert attachment_dir.joinpath("proof.txt").read_text(encoding="utf-8") == "attachment payload"
    assert not cold.cold_archive_package_path(session.session_id).exists()


def test_restore_retries_after_process_death_following_attachment_publication(
    isolated_session_store, monkeypatch
):
    tmp_path, session_dir = isolated_session_store
    session = _session("cold_restore_process_death")
    session.save(touch_updated_at=False)
    attachment_dir = _write_hot_artifacts(tmp_path, session_dir, session.session_id)
    cold.cold_archive_session(session)
    loaded = models.Session.load(session.session_id)
    assert loaded is not None
    original_atomic_write_json = cold._atomic_write_json

    def die_before_sidecar(path, payload):
        if path == loaded.path:
            raise SystemExit("simulated process death")
        return original_atomic_write_json(path, payload)

    monkeypatch.setattr(cold, "_atomic_write_json", die_before_sidecar)
    with pytest.raises(SystemExit, match="process death"):
        cold.restore_cold_archived_session(loaded)

    assert attachment_dir.joinpath("proof.txt").read_text(encoding="utf-8") == "attachment payload"
    stub = json.loads(loaded.path.read_text(encoding="utf-8"))
    assert isinstance(stub.get("cold_archive"), dict)
    assert cold.cold_archive_package_path(session.session_id).exists()

    monkeypatch.setattr(cold, "_atomic_write_json", original_atomic_write_json)
    retried = models.Session.load(session.session_id)
    cold.restore_cold_archived_session(retried)
    assert attachment_dir.joinpath("proof.txt").read_text(encoding="utf-8") == "attachment payload"
    assert not cold.cold_archive_package_path(session.session_id).exists()


@pytest.mark.skipif(os.name == "nt", reason="Symlink semantics require POSIX")
def test_archive_rejects_attachment_symlinks_without_copying_external_data(
    isolated_session_store,
):
    tmp_path, session_dir = isolated_session_store
    session = _session("archive_attachment_symlink")
    session.save(touch_updated_at=False)
    original = session.path.read_bytes()
    external = tmp_path / "outside-secret.txt"
    external.write_text("outside-secret", encoding="utf-8")
    attachment_dir = session_dir.parent / "attachments" / session.session_id
    attachment_dir.mkdir(parents=True)
    attachment_dir.joinpath("escape.txt").symlink_to(external)

    with pytest.raises(cold.ColdArchiveError, match="symbolic link"):
        cold.cold_archive_session(session)

    assert session.path.read_bytes() == original
    assert not cold.cold_archive_package_path(session.session_id).exists()
    assert external.read_text(encoding="utf-8") == "outside-secret"


def test_corrupt_or_missing_cold_package_fails_closed_but_sidebar_stub_survives(
    isolated_session_store,
):
    _tmp_path, _session_dir = isolated_session_store
    session = _session("cold_corrupt")
    session.save(touch_updated_at=False)
    cold.cold_archive_session(session)
    package = cold.cold_archive_package_path(session.session_id)
    (package / "session.json").write_text("{}", encoding="utf-8")

    with pytest.raises(cold.ColdArchiveError, match="verification"):
        models.Session.load(session.session_id)
    metadata = models.Session.load_metadata_only(session.session_id)
    assert metadata is not None
    assert metadata.archived is True
    assert metadata._metadata_message_count == 2

    shutil.rmtree(package)
    with pytest.raises(cold.ColdArchiveError, match="missing"):
        models.Session.load(session.session_id)


def test_delete_cleanup_removes_cold_package(isolated_session_store):
    _tmp_path, _session_dir = isolated_session_store
    session = _session("cold_delete")
    session.save(touch_updated_at=False)
    cold.cold_archive_session(session)
    package = cold.cold_archive_package_path(session.session_id)
    assert package.exists()

    cold.delete_cold_archive_artifacts(session.session_id)
    assert not package.exists()
    # Idempotent explicit delete cleanup.
    cold.delete_cold_archive_artifacts(session.session_id)


def test_http_archive_open_unarchive_delete_round_trip(test_server):
    del test_server
    sid = "hermesui_cold_http"
    hot_path = models.SESSION_DIR / f"{sid}.json"
    package = cold.cold_archive_package_path(sid)
    models._clear_webui_deleted_session_tombstone(sid)
    shutil.rmtree(package, ignore_errors=True)
    hot_path.unlink(missing_ok=True)
    hot_path.with_suffix(".json.bak").unlink(missing_ok=True)
    shutil.rmtree(upload._session_attachment_dir(sid), ignore_errors=True)

    session = _session(sid)
    session.save(touch_updated_at=False)
    attachment_dir = upload._session_attachment_dir(sid)
    attachment_dir.mkdir(parents=True)
    (attachment_dir / "http-proof.txt").write_text("round trip", encoding="utf-8")
    try:
        archived, status = _post("/api/session/archive", {"session_id": sid, "archived": True})
        assert status == 200, archived
        assert archived["session"]["archived"] is True
        stub = json.loads(hot_path.read_text(encoding="utf-8"))
        assert stub["messages"] == []
        assert package.is_dir()
        assert not attachment_dir.exists()

        opened, status = _get(f"/api/session?session_id={sid}&messages=1&resolve_model=0")
        assert status == 200, opened
        assert opened["session"]["messages"] == session.messages
        assert json.loads(hot_path.read_text(encoding="utf-8"))["messages"] == []
        with models.LOCK:
            assert sid not in models.SESSIONS

        restored, status = _post("/api/session/archive", {"session_id": sid, "archived": False})
        assert status == 200, restored
        assert restored["session"]["archived"] is False
        assert json.loads(hot_path.read_text(encoding="utf-8"))["messages"] == session.messages
        assert attachment_dir.joinpath("http-proof.txt").read_text(encoding="utf-8") == "round trip"
        assert not package.exists()

        deleted, status = _post("/api/session/delete", {"session_id": sid})
        assert status == 200, deleted
        assert not hot_path.exists()
        assert not package.exists()
        with pytest.raises(RuntimeError, match="Refusing to save deleted session"):
            session.save(touch_updated_at=False)
    finally:
        _post("/api/session/delete", {"session_id": sid})
        shutil.rmtree(package, ignore_errors=True)
        hot_path.unlink(missing_ok=True)
        hot_path.with_suffix(".json.bak").unlink(missing_ok=True)
        shutil.rmtree(attachment_dir, ignore_errors=True)


def test_http_archive_refuses_pending_session_without_creating_package(test_server):
    del test_server
    sid = "hermesui_cold_http_busy"
    hot_path = models.SESSION_DIR / f"{sid}.json"
    package = cold.cold_archive_package_path(sid)
    models._clear_webui_deleted_session_tombstone(sid)
    shutil.rmtree(package, ignore_errors=True)
    hot_path.unlink(missing_ok=True)
    session = _session(sid)
    session.pending_user_message = "still running"
    session.save(touch_updated_at=False)
    before = hot_path.read_bytes()
    try:
        response, status = _post("/api/session/archive", {"session_id": sid, "archived": True})
        assert status == 409, response
        assert hot_path.read_bytes() == before
        assert not package.exists()
    finally:
        _post("/api/session/delete", {"session_id": sid})
        shutil.rmtree(package, ignore_errors=True)
        hot_path.unlink(missing_ok=True)
