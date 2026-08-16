# Give this prompt to your AI

The fenced text below is the exact Humanity Labs install prompt.

```text
Install HermesUI v0.1.1 from https://github.com/humanitylabs-org/HermesUI on this Hermes device and expose it privately at /hermesUI.

Complete and verify the installation:

1. Check that the host is Linux with Python 3.11, 3.12, or 3.13, git, curl, systemd user services, `systemd-analyze`, Hermes Agent, and Tailscale. Confirm Hermes works with `hermes --version` and `hermes doctor`. Tailscale is mandatory and must be connected with MagicDNS. If a prerequisite is missing, explain one safe fix at a time. Ask before running sudo, a package manager, or the official Tailscale installer. Never enable Funnel.

2. Clone the repository at reviewed tag `v0.1.1` into `~/apps/HermesUI`, or safely update an existing clean checkout to that exact tag. Do not overwrite unrelated local changes. Verify `git describe --tags --exact-match` returns `v0.1.1`. Resolve the immutable reviewed commit with `expected_commit="$(git rev-parse 'v0.1.1^{commit}')"`, verify `git rev-parse HEAD` returns that exact full commit, and verify `git ls-remote origin 'refs/tags/v0.1.1^{}'` reports the same commit. Refuse to continue if any value differs.

3. Run `./scripts/tailnet-prereq-check.sh`, resolve any failure safely, then run `./scripts/tailnet-setup.sh`.

4. Verify `hermesui-launcher.service` is enabled and `hermesui.service` is active. Run `./scripts/tailnet-status.sh` to verify the exact managed process. Verify `http://127.0.0.1:8793/health` reports healthy and the server is bound only to loopback. If the installer selected another port, use that exact port for every check.

5. Verify the canonical private Tailnet URL `https://<this-device>.ts.net/hermesUI/` loads exactly as written. Verify `/hermesUI/health` is healthy and `/hermesUI/manifest.json` identifies HermesUI with relative `id`, `start_url`, and `scope` values that remain contained under `/hermesUI` when installed as a PWA. Confirm the Serve configuration exposes `/hermesUI` only and that Funnel is not enabled.

6. Treat anyone who can open HermesUI as a trusted operator of this Hermes account. If this Tailnet includes people who should not control the agent, help me enable the WebUI password without asking me to paste the password into chat, and recommend a narrow Tailscale grant or ACL.

7. Report the installed tag and commit, service state, loopback bind, local health evidence, Tailnet health evidence, final URL, and exact uninstall command `./scripts/tailnet-uninstall.sh`. Do not claim success until every check passes.

Preserve existing Hermes conversations, profiles, configuration, credentials, workspaces, and gateway services. Do not publish the app to the internet, enable Funnel, print secrets, or silently replace a different service already using the selected port or `/hermesUI` path.
```
