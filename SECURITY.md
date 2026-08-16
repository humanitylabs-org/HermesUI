# Security

## Supported release

HermesUI is an early preview. Only the latest published release tag receives security fixes.

## Deployment boundary

HermesUI controls a Hermes Agent account and may expose conversations, files, tools, memories, configuration, and agent-usable credentials. Anyone who can use the app should be treated as a trusted operator of that Hermes account.

The supported installer binds HermesUI to `127.0.0.1` and publishes only `/hermesUI` through Tailscale Serve. Never enable Tailscale Funnel for HermesUI. Use Tailscale grants or ACLs to limit which Tailnet identities can reach the host, and enable the WebUI password when Tailnet membership is broader than the intended operators.

HermesUI does not replace host security, Tailscale identity controls, or Hermes Agent's own authentication and approval boundaries.

## Reporting

Use GitHub's private vulnerability reporting for this repository. Do not open a public issue containing an exploit, credential, private Tailnet hostname, conversation, or workspace data.

For vulnerabilities that also affect the upstream Hermes WebUI, follow the upstream project's current security-reporting process as well.
