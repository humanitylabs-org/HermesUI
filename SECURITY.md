# Security

## Supported release

HermesUI is an early preview. Only the latest published release tag receives security fixes.

## Deployment boundary

HermesUI controls a Hermes Agent account and may expose conversations, files, tools, memories, configuration, and agent-usable credentials. Anyone who can use the app should be treated as a trusted operator of that Hermes account.

The supported installers bind HermesUI to `127.0.0.1`. New VPS installs prefer a dedicated Cloudflare Tunnel protected by a self-hosted Access application with exact-email allow rules; the tunnel also requires Access JWT validation at the origin connector. The management token is read only from an owner-only local file and is never stored in the repository or printed. Existing healthy Tailscale installations stay on Tailscale Serve, and new Tailscale installs require an explicit choice. Never enable Tailscale Funnel for HermesUI. Use Access policies or Tailscale grants/ACLs to limit operators, and enable the WebUI password when the selected identity boundary is broader than the intended operators.

The unchanged upstream backend scopes its cookies to the whole origin (`Path=/`). HermesUI gives its session and profile cookies unique names to avoid collisions. Cloudflare mode therefore uses a dedicated hostname. In Tailscale mode, sibling paths on the same MagicDNS origin must be equally trusted; use a dedicated MagicDNS origin when that is not true. OIDC callbacks are not supported through the shared `/hermesUI` mount without upstream backend support; password and passkey authentication remain supported.

HermesUI does not replace host security, Tailscale identity controls, or Hermes Agent's own authentication and approval boundaries.

## Reporting

Use GitHub's private vulnerability reporting for this repository. Do not open a public issue containing an exploit, credential, private Tailnet hostname, conversation, or workspace data.

For vulnerabilities that also affect the upstream Hermes WebUI, follow the upstream project's current security-reporting process as well.
