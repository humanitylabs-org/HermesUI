# Give this prompt to your AI

This is the release prompt template. The published AI Wizards page and release asset replace `REVIEWED_COMMIT_SHA` with the reviewed 40-character commit before anyone copies it. Do not use this unresolved template directly.

```text
Install or replace Wizard App v0.4.0 from https://github.com/humanitylabs-org/HermesUI on this Linux Hermes device. This release contains the current Wizard App interface. An existing managed Wizard App installation must be updated even when it is healthy.

Preserve Hermes completely: never delete, move, reset, rewrite, or create a second copy of the active `HERMES_HOME`; preserve every conversation, profile, credential, memory, workspace, scheduled task, gateway, and provider configuration. This operation replaces Wizard App code and its owned runtime only, not Hermes Agent or Hermes data.

1. Inspect the host, active Hermes/WebUI processes, `~/.config/hermesui/install.env`, the installed user units, the existing Wizard App checkout, its Git status, selected `HERMES_HOME`, profile, loopback port, and current Cloudflare or Tailscale access mode. Refuse to touch a dirty or foreign checkout or a unit that cannot be proven installer-owned. Never start a second WebUI over the same `HERMES_HOME`.

2. Set `expected_commit="REVIEWED_COMMIT_SHA"` and refuse to continue unless it is exactly 40 lowercase hexadecimal characters. Clone the repository into a new temporary owner-only release checkout, check out annotated tag `v0.4.0`, and verify that `git describe --tags --exact-match` returns `v0.4.0`. Verify that `git rev-parse HEAD`, `git rev-parse 'v0.4.0^{commit}'`, and the peeled commit from `git ls-remote origin 'refs/tags/v0.4.0^{}'` all equal the literal `expected_commit`.

3. If `~/.config/hermesui/install.env` records an existing managed installation, determine its exact checkout path from the verified installer-owned unit. Run the release checkout's updater against that installed checkout:

   HERMESUI_REPO_ROOT_OVERRIDE="/exact/existing/checkout" \
     "/exact/release/checkout/hermesui/installer/update.sh" \
     v0.4.0 "$expected_commit"

   The updater must dispatch to the existing access mode, wait for zero active runs and streams, preserve its exact `HERMES_HOME`, profile, port, hostname, tunnel, Access policy, Tailnet route, and service state, replace the clean checkout at the reviewed commit, and roll back the checkout, owned unit, and runtime on failure. Do not request a Cloudflare token for this code-only replacement and do not recreate provider resources.

4. If no managed Wizard App exists, install from the verified v0.4.0 checkout. Run `hermes --version` and `hermes doctor`. The installer supports Linux, Python 3.11–3.13, git, curl, Hermes Agent, and systemd user services. Ask before sudo, package-manager commands, installing cloudflared or Tailscale, or enabling user lingering.

5. For a new VPS install, prefer Cloudflare Tunnel + Access. Ask for a dedicated hostname, exact allowed operator email address or addresses, Cloudflare account ID and zone ID, and an owner-only local API-token file; never paste or print the token. Then run `./hermesui/installer/setup.sh --mode cloudflare` with the confirmed `--account-id`, `--zone-id`, `--hostname`, repeated `--allow-email`, and `--api-token-file` arguments. Use Tailscale only if I explicitly choose it, via `./hermesui/installer/setup.sh --mode tailscale`; never enable Funnel.

6. Verify the exact result. Confirm the installed checkout is detached at `v0.4.0` and `expected_commit`; the selected Wizard App service is enabled/active as appropriate; the server binds only to its recorded `127.0.0.1` port; `/health` is healthy; no second Hermes execution backend exists; and the prior `HERMES_HOME` and profile are still selected. Run `cloudflare-status.sh` or `tailnet-status.sh` for the recorded mode. Compare the served `static/ui.js`, `static/sessions.js`, `static/sw.js`, and `static/tailnet-app-rail.js` SHA-256 values with those files in the verified release checkout, then have me open the private URL and confirm the current Wizard App interface loads without broken assets or browser errors.

7. Report the prior and installed commits, access mode, final private URL, loopback bind, service states, health evidence, served-asset verification, preserved Hermes home/profile, and rollback result or command. Do not claim success unless the update or install and every selected-mode check pass.

Never expose a public origin, weaken Cloudflare Access or Tailscale policy, enable Funnel, print secrets, overwrite a foreign service, or modify Hermes data.
```
