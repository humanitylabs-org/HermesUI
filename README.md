# HermesUI

HermesUI is an early-preview, mobile-first interface for [Hermes Agent](https://hermes-agent.nousresearch.com/). It keeps the full Hermes conversation runtime while simplifying the browser shell around sessions, chat, and settings.

This project is intentionally available early so people can test it while the interface is still evolving. Expect frequent updates.

## What is different

- Sessions are the starting point on mobile. The app never invents a fake `Chat` tab.
- New Chat opens a real `Untitled` session immediately so it can be renamed.
- Mobile session tabs use the same state indicators as the session list.
- Tapping or swiping between sessions uses the same content-skeleton transition.
- Horizontal session swipes do not begin from text fields or other interactive controls.
- Settings opens as an accessible popup on desktop and mobile.
- The optional session dashboard leaves the original transcript intact and has a Classic escape hatch.

## Requirements

The supported Tailnet installer target is currently Linux with:

- Python 3.11, 3.12, or 3.13
- Hermes Agent installed and working
- Tailscale connected with MagicDNS
- systemd user services and `systemd-analyze`
- Git and curl

HermesUI binds only to `127.0.0.1` and is exposed privately through Tailscale Serve. The installer never enables Funnel.

## Install on a Tailnet

Install a reviewed release tag rather than a moving branch:

```bash
mkdir -p ~/apps
git clone --branch v0.1.0 --depth 1 https://github.com/humanitylabs-org/HermesUI.git ~/apps/HermesUI
cd ~/apps/HermesUI
./scripts/tailnet-prereq-check.sh
./scripts/tailnet-setup.sh
```

The default private URL is:

```text
https://<this-device>.ts.net/hermesUI/
```

The local server listens on `127.0.0.1:8793`. Override the port before setup when necessary:

```bash
HERMESUI_PORT=8794 ./scripts/tailnet-setup.sh
```

## Give this prompt to your AI

The canonical Humanity Labs installation prompt is in [docs/Tailnet-HermesUI-Prompt.md](docs/Tailnet-HermesUI-Prompt.md). The legacy prompt path remains byte-identical for compatibility.

## Status, update, and uninstall

```bash
./scripts/tailnet-status.sh
./scripts/update.sh v0.1.0
./scripts/tailnet-uninstall.sh
```

`update.sh` requires an explicit reviewed tag, refuses to overwrite local changes, and restarts the service onto the reviewed bytes. Uninstall removes only the installer-owned user service and `/hermesUI` Serve route; it exits non-zero if cleanup is incomplete. It does not delete Hermes conversations, configuration, credentials, or this repository.

## Security boundary

HermesUI can operate the same Hermes Agent account that owns your conversations, workspaces, memories, tools, and credentials. Treat access as trusted operator access. Keep it on a private Tailnet, restrict access with Tailscale grants or ACLs, and enable the WebUI password when the Tailnet includes people who should not control your agent.

Do not expose HermesUI with Tailscale Funnel or a public reverse proxy. See [SECURITY.md](SECURITY.md) for reporting and deployment guidance.

## Development

The focused HermesUI checks are:

```bash
python3 -m pytest -q \
  tests/test_hermesui_chat_shell.py \
  tests/test_hermesui_mobile_session_swipe.py \
  tests/test_hermesui_session_dashboard.py \
  tests/test_hermesui_sessions_sidebar.py \
  tests/test_hermesui_settings_popup.py
python3 scripts/privacy-check.py
./qa/tailnet-installer-smoke.sh
```

The upstream-derived test runner remains available as `./scripts/test.sh`, but it includes historical assertions for the original Nesquena shell. The focused HermesUI checks above are the release contract for this fork.

## Attribution and license

HermesUI is derived from [Hermes WebUI by Nesquena](https://github.com/nesquena/hermes-webui) and preserves its MIT license and contributor history in the distributed source files. See [NOTICE.md](NOTICE.md) and [LICENSE](LICENSE).
