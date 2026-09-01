# Give this prompt to your AI

This is the release prompt template. The published AI Wizards page and release asset replace `REVIEWED_COMMIT_SHA` with the independently reviewed 40-character commit before anyone copies it. Do not use this unresolved template directly.

```text
Instal...[truncated]

Use one private-access mode only:
- If Wizard App is already installed through a healthy Tailscale Serve route recorded in `~/.config/hermesui/install.env`, preserve that route and URL. Do not add Cloudflare.
- For a new VPS install, use Cloudflare Tunnel + Access. This is the preferred mode even when Tailscale is installed.
- Use Tailscale for a new install only if I explicitly choose it. Never enable Funnel.

Complete and verify the installation:

1. Inspect the host, the existing Hermes/WebUI processes, `~/.config/hermesui/install.env`, and any existing checkout. Preserve all Hermes conversations, profiles, configuration, credentials, workspaces, and gateway services. Do not overwrite a dirty checkout or start a second WebUI over the same `HERMES_HOME`. If a healthy Wizard App installation already exists, preserve it and report its current version and access mode; this setup prompt is not an authorization to migrate or update it.

2. For a new install, set `expected_commit="REVIEWED_COMMIT_SHA"`. Refuse to continue unless it is exactly 40 lowercase hexadecimal characters. Clone the repository into a new `~/apps/HermesUI` checkout, then check out reviewed tag `v0.3.1`. Verify that `git describe --tags --exact-match` returns `v0.3.1` and that `git rev-parse HEAD`, `git rev-parse 'v0.3.1^{commit}'`, and the peeled commit from `git ls-remote origin 'refs/tags/v0.3.1^{}'` all equal the literal `expected_commit`.

3. Run `hermes --version` and `hermes doctor`. The installer supports Linux, Python 3.11–3.13, git, curl, Hermes Agent, and systemd user services. Ask before sudo, package-manager commands, installing cloudflared or Tailscale, or enabling user lingering. Resolve one prerequisite at a time.

4. For a new Cloudflare install, ask me for a dedicated hostname under a zone I control and the exact email address or addresses allowed to operate this Hermes account. Treat those users as trusted operators. Obtain the Cloudflare account ID and zone ID. Have me save a narrowly scoped Cloudflare API token in a local owner-only regular file without pasting it into chat; the token needs account permissions Cloudflare Tunnel: Edit, Access: Apps and Policies: Edit, and Access: Organizations, Identity Providers, and Groups: Read, plus zone permission DNS: Edit for the selected zone. Confirm the account has a Zero Trust organization and the Cloudflare One-Time PIN identity provider enabled. Confirm the hostname, operator emails, account ID, zone ID, token path, and the planned ne...[truncated]

   ./hermesui/installer/setup.sh --mode cloudflare \
     --account-id ACCOUNT_ID \
     --zone-id ZONE_ID \
     --hostname wizard.example.com \
     --allow-email owner@example.com \
     --api-token-file ~/.config/hermesui/cloudflare-api-token

   Repeat `--allow-email` for each approved operator. Do not put the API token itself in the command line. The installer must create Access and its allow policy before DNS, create a dedicated remotely managed Tunnel, require Access JWT validation at the origin connector, keep the WebUI on `127.0.0.1:8793`, install persistent user services, and fail closed or roll back only the resources it created.

5. For an explicitly approved new Tailscale install, run `./hermesui/installer/setup.sh --mode tailscale`. Confirm MagicDNS is enabled, `/hermesUI` is the only Serve path this installer owns, and Funnel remains disabled. Do not add Cloudflare to an existing healthy Tailscale installation.

6. Verify the exact selected mode. For Cloudflare, run `./hermesui/installer/cloudflare-status.sh`, verify both user services are enabled and active, verify local `/health`, confirm an unauthenticated request is intercepted by Cloudflare Access, then have me authenticate and confirm the Wizard App loads. For Tailscale, run `./hermesui/installer/tailnet-status.sh` and verify the local and Tailnet health URLs. In either mode, confirm there is no public host bind, no second Hermes execution backend, no broken images or browser errors, and that a restart preserves sessions and settings.

7. Report the installed tag and commit, access mode, final private URL, loopback bind, service states, local and private-access health evidence, and rollback command. For Cloudflare the rollback command is `./hermesui/installer/cloudflare-uninstall.sh --api-token-file PATH`; for Tailscale it is `./hermesui/installer/tailnet-uninstall.sh`. Do not claim success until every selected-mode check passes. If setup reports retained recovery state, do not rerun setup; after provider connectivity is restored, run the Cloudflare uninstall command first so the installer can reconcile and remove only its exact resources.

Never print secrets, weaken Access or Tailscale policy, expose the origin publicly, enable Funnel, silently replace another service, or create competing Cloudflare and Tailscale routes.
```
