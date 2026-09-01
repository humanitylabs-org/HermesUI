# Give this prompt to your AI

This is the release prompt template. The published Humanity Labs page and release asset replace `REVIEWED_COMMIT_SHA` with the independently reviewed 40-character commit before anyone copies it. Do not use this unresolved template directly.

```text
Install HermesUI v0.3.0 from https://github.com/humanitylabs-org/HermesUI on this Hermes device and expose it privately at /hermesUI.

Complete and verify the installation:

1. Check that the host is Linux with Python 3.11, 3.12, or 3.13, git, curl, systemd user services, `systemd-analyze`, Hermes Agent, and Tailscale. Confirm Hermes works with `hermes --version` and `hermes doctor`. Tailscale is mandatory and must be connected with MagicDNS. If a prerequisite is missing, explain one safe fix at a time. Ask before running sudo, a package manager, or the official Tailscale installer. Never enable Funnel.

2. Set `expected_commit="REVIEWED_COMMIT_SHA"` and refuse to continue if that value is not exactly 40 lowercase hexadecimal characters. Clone the repository at reviewed tag `v0.3.0` into `~/apps/HermesUI`, or safely update an existing clean checkout to that exact tag. Do not overwrite unrelated local changes. Verify `git describe --tags --exact-match` returns `v0.3.0`. Verify `git rev-parse HEAD`, `git rev-parse 'v0.3.0^{commit}'`, and the peeled commit reported by `git ls-remote origin 'refs/tags/v0.3.0^{}'` all equal the literal `expected_commit`. Refuse to continue if any value differs.

3. Run `./hermesui/installer/tailnet-prereq-check.sh`, resolve any failure safely, then run `./hermesui/installer/tailnet-setup.sh`. This release supports standalone mode only. If setup reports another or ambiguous Hermes/WebUI execution process using the resolved `HERMES_HOME`, stop and report the conflict without mutation. Do not choose another port, start a second backend, copy credentials into an isolated home, or attempt external/client-only attachment.

4. Verify `hermesui-launcher.service` is enabled and `hermesui.service` is active. Run `./hermesui/installer/tailnet-status.sh` to verify the exact managed process, standalone mode, resolved Hermes home, and default profile. Verify the loopback `/health` endpoint on the port recorded in `~/.config/hermesui/install.env`; never infer safety from port separation alone.

5. Verify the canonical private Tailnet URL `https://<this-device>.ts.net/hermesUI/` loads exactly as written. Verify `/hermesUI/health` is healthy and `/hermesUI/manifest.json` identifies HermesUI with relative `id`, `start_url`, and `scope` values that remain contained under `/hermesUI` when installed as a PWA. Confirm the Serve configuration exposes `/hermesUI` only and that Funnel is not enabled.

6. Treat anyone who can open HermesUI as a trusted operator of this Hermes account. The unchanged upstream backend scopes its cookies to the whole origin (`Path=/`), so use a dedicated MagicDNS origin if sibling paths are not equally trusted. Mounted OIDC callbacks are not supported without upstream backend changes; use password or passkey authentication. If this Tailnet includes people who should not control the agent, help me enable the WebUI password without asking me to paste the password into chat, and recommend a narrow Tailscale grant or ACL.

7. Report the installed tag and commit, service state, loopback bind, local health evidence, Tailnet health evidence, final URL, and exact uninstall command `./hermesui/installer/tailnet-uninstall.sh`. Do not claim success until every check passes.

Preserve existing Hermes conversations, profiles, configuration, credentials, workspaces, and gateway services. Do not publish the app to the internet, enable Funnel, print secrets, or silently replace a different service already using the selected port or `/hermesUI` path.
```
