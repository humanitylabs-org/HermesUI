# HermesUI Native Session Cold Archive Contract

HermesUI's interactive Archive action is a storage-tier transition for settled, native WebUI sessions. It is not deletion and it does not alter Hermes gateway `state.db`.

## Ownership and scope

Only native, writable WebUI sessions enter cold storage. Imported CLI/TUI/API sessions, messaging-channel sessions, cron sessions, delegated subagent sessions, and read-only records keep the upstream metadata-only archive behavior because their authoritative transcript may live outside HermesUI.

Archiving is refused while a session has persisted pending/stream state, a runtime worker, or a registered writeback owner. The per-session agent lock is acquired with a bounded timeout before the transition.

## Storage layout

The hot store keeps `sessions/<session_id>.json` as a compact sidebar stub containing ordinary metadata, the original message count, a versioned `cold_archive` marker, and an empty `messages` sentinel. It contains no transcript, context transcript, tool-call payloads, or activity-scene bodies.

The cold package is stored on the same filesystem at `cold_archive/sessions/<session_id>/` and contains:

- `session.json`: the complete archived session payload.
- `source-backup.json`: the pre-existing sidecar backup, when present.
- `attachments/`: the session attachment tree, when present.
- `manifest.json`: schema, session ID, creation time, artifact sizes, and SHA-256 checksums.

Run and turn journals are recovery artifacts rather than conversation records. They are removed from the hot store only after the package and stub commit, and they are not restored.

## State transitions

Archive stages and fsyncs a complete package, atomically publishes the package directory, and verifies every manifested artifact. The verified package becomes the rollback source, so the ordinary hot `.json.bak` is removed before the compact stub is published; startup recovery can therefore never misread the intentional empty-message stub as data loss. Attachments and journals are removed only after the stub commit. A failure before stub publication leaves the original full hot sidecar authoritative alongside the verified duplicate package.

Sidebar metadata loads read only the stub. Opening an archived conversation verifies and reads the cold transcript without rewriting the hot sidecar. Metadata changes made while viewing an archived session rotate the archive generation and reject stale writers; a previous transcript generation allows recovery if the manifest update is interrupted.

Unarchive verifies the package, restores attachments through a staged atomic rename, writes and verifies the full unarchived sidecar, and removes the package only after the hot copy is authoritative. If a process dies after attachment publication, an exact verified live tree is recognized and the restore is retryable; a mismatched live tree still fails closed. Recovery journals remain absent. Explicit session deletion removes both the hot stub and any cold package while preserving the existing worktree-retention contract.

## Failure policy

Missing, malformed, incompatible, or checksum-invalid packages fail closed. HermesUI must not claim success, accept unverified transcript bytes, or silently replace a live attachment tree. Duplicate cold data left by a crash after a successful restore is treated as a stale verified generation and cleaned before the next archive. Archive and delete cleanup are idempotent.

No startup migration is performed. Existing archived sessions retain their current representation until an operator explicitly archives them through the updated action.

## Hot-session cache boundary

The browser may prewarm a bounded recent-message tail for up to five unarchived sessions in the active profile. An idle snapshot is reusable only while its list revision is unchanged; a live snapshot is reusable only for the exact same active stream ID, with the run journal remaining authoritative for subsequent activity. Archived rows are never prewarmed or stored in this cache, and data-saver clients skip prewarming entirely.
