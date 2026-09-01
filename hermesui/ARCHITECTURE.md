# Hermes UI architecture contract

Hermes UI is not a replacement backend for Hermes Agent. It is a frontend distribution layered over Nesquena's Hermes WebUI.

## Layer 1: upstream WebUI

`UPSTREAM.json` pins the exact Nesquena repository, commit, tree, and tag used by this release line. Every upstream-owned backend/runtime file must remain identical to that tree, including:

- `api/`
- `server.py`, `bootstrap.py`, and `mcp_server.py`
- Python requirements, lockfiles, and package metadata
- authentication, sessions, persistence, streaming, providers, and Hermes Agent integration
- upstream Docker/runtime files

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

## Layer 3: private-access composition

`hermesui/installer/` is an operational wrapper, not a backend fork. It:

- checks for Linux, Python, Hermes Agent, and systemd user services;
- runs the unchanged upstream WebUI server from the reviewed Hermes UI checkout;
- binds the server to loopback;
- prefers a dedicated Cloudflare Tunnel + Access boundary for a new VPS install;
- creates Access and its exact-email allow policy before DNS and requires Access JWT validation again at the origin connector;
- preserves an existing healthy Tailscale Serve installation and supports a new Tailscale install only by explicit choice;
- provides scoped status, update, and uninstall operations;
- does not enable Funnel, create a temporary public tunnel, or modify Hermes Agent data.

The installer never patches files under `api/` or changes the upstream request/response contract.

## Downstream verification and release wiring

Hermes UI keeps Nesquena's test, browser, documentation, and Docker checks. The downstream overlay workflow runs for every pull request and push, while inherited workflow overrides are hash-pinned by `hermesui/check_boundary.py`; none changes application runtime behavior.

The inherited tag-triggered release and GHCR publisher is disabled on the downstream line. `.github/workflows/release.yml` is a read-only manual preflight for an exact reviewed commit. Publishing a tag, GitHub Release, package, image, website prompt, or deployment remains a separate human-approved action.

## Humanity Labs button

The aiwizards.com button should copy or launch the reviewed prompt from `docs/give-this-prompt-to-your-ai.md`. The user's AI performs prerequisite checks, clones an immutable reviewed Hermes UI release, chooses the supported access mode under the documented rules, runs the matching installer, and reports the private URL. The website does not host the user's agent or proxy their traffic.

## Release invariant

A normal Hermes UI release is valid only when all of these are true:

- the pinned upstream commit is an ancestor of the release;
- `python3 hermesui/check_boundary.py` passes;
- no upstream backend/runtime path differs from `UPSTREAM.json`;
- the frontend overlay hashes match the shipped files;
- frontend and mounted-subpath browser tests pass;
- Cloudflare install/status/uninstall and Tailscale install/status/update/uninstall smokes pass;
- an independent review confirms the exact immutable commit.
