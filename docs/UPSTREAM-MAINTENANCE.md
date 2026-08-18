# Updating Hermes UI from upstream

Hermes UI tracks Nesquena's Hermes WebUI while keeping the normal release line frontend-only. `UPSTREAM.json` is the machine-readable anchor; `hermesui/check_boundary.py` is the enforcement gate.

## Branches

- `upstream/master`: fetched directly from `https://github.com/nesquena/hermes-webui.git`.
- `upstream-sync`: reviewed local pointer to the exact upstream commit recorded in `UPSTREAM.json`.
- `hermes-ui-v0.2-frontend-only`: Humanity Labs frontend plus the isolated Tailnet installer.
- `refresh/<upstream-tag>`: disposable branch for one upstream update.
- `backend-experiment/*`: optional research only; never merge into the normal release line.

## Refresh procedure

1. Start with a clean `hermes-ui-v0.2-frontend-only` checkout and verify the `upstream` remote URL.
2. Fetch `upstream` without force-updating tags.
3. Select one exact reviewed upstream commit and record its full commit, tree, and tag.
4. Fast-forward `upstream-sync` to that exact commit; never rewrite it to a different tree under the same review.
5. Create `refresh/<upstream-tag>` from the current Hermes UI tip and merge the exact `upstream-sync` commit. Resolve conflicts only under `static/` or downstream-owned `hermesui/`, `qa/`, docs, and Hermes UI tests. Do not resolve a backend conflict by keeping a Humanity Labs version; the upstream file wins.
6. Update `UPSTREAM.json` to the new commit, tree, and tag.
7. Reconcile frontend changes against the new upstream assets, preserving upstream browser fixes semantically.
8. Run:

```bash
python3 hermesui/update_overlay_manifest.py
python3 hermesui/check_boundary.py
```

9. Compare the old and new frontend overlays. Every changed `static/` path must be intentional, and no backend/runtime path may appear.
10. Run the frontend, mounted-subpath, browser, and Tailnet installer tests. Run upstream backend tests from the unchanged new upstream tree as a parity check.
11. Freeze the exact candidate commit and obtain independent review before merging or releasing.

## What never belongs on the normal line

Do not modify `api/`, server entry points, authentication, persistence, session storage, streaming, provider routing, requirements, lockfiles, package metadata, upstream Docker files, or unrelated upstream workflows. Contribute those changes upstream or keep them on an explicitly separate experiment branch.
