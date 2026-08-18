# Hermes UI architecture contract

Hermes UI is not a replacement backend for Hermes Agent. It is a frontend distribution layered over Nesquena's Hermes WebUI.

## Layer 1: upstream WebUI

`UPSTREAM.json` pins the exact Nesquena repository, commit, tree, and tag used by this release line. Every upstream-owned backend/runtime file must remain identical to that tree, including:

- `api/`
- `server.py`, `bootstrap.py`, and `mcp_server.py`
- Python requirements, lockfiles, and package metadata
- authentication, sessions, persistence, streaming, providers, and Hermes Agent integration
- upstream Docker/runtime files and upstream CI workflows

Hermes UI does not carry fixes for those files. Backend changes belong upstream or on a separate experiment branch that is never merged into the normal release line.

## Layer 2: frontend overlay

Humanity Labs owns the browser assets changed under `static/`. `hermesui/frontend-overlay.json` records the exact upstream and Hermes UI SHA-256 hashes for every changed frontend file.

After changing the frontend:

```bash
python3 hermesui/update_overlay_manifest.py
python3 hermesui/check_boundary.py
```

The first command refreshes the overlay inventory. The second rejects backend drift, unapproved upstream-file changes, unrecorded frontend files, and stale hashes.

Frontend tests use downstream-specific names under `tests/test_hermes_ui_*` and `tests/test_hermesui_subpath_*`. Upstream tests are not rewritten to make the custom interface pass.

## Layer 3: Tailnet composition

`hermesui/installer/` is an operational wrapper, not a backend fork. It:

- checks for Linux, Python, Hermes Agent, systemd user services, and Tailscale;
- runs the unchanged upstream WebUI server from the reviewed Hermes UI checkout;
- binds the server to loopback;
- exposes only `/hermesUI` through Tailscale Serve;
- provides scoped status, update, and uninstall operations;
- does not enable Funnel or modify Hermes Agent data.

The installer never patches files under `api/` or changes the upstream request/response contract.

## Humanity Labs button

The humanitylabs.org button should copy or launch the reviewed prompt from `docs/give-this-prompt-to-your-ai.md`. The user's AI performs prerequisite checks, clones an immutable reviewed Hermes UI release, runs the Tailnet installer, and reports the private URL. The website does not host the user's agent or proxy their traffic.

## Release invariant

A normal Hermes UI release is valid only when all of these are true:

- the pinned upstream commit is an ancestor of the release;
- `python3 hermesui/check_boundary.py` passes;
- no upstream backend/runtime path differs from `UPSTREAM.json`;
- the frontend overlay hashes match the shipped files;
- frontend and mounted-subpath browser tests pass;
- Tailnet install/status/update/uninstall smokes pass;
- an independent review confirms the exact immutable commit.
