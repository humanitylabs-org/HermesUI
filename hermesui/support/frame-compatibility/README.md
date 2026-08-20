# HermesUI frame-compatibility checker

This optional adjacent service lets the browser-local WORK and WEB selectors choose between the normal iframe panel and a regular browser tab before navigation.

It is deliberately not part of the inherited Hermes WebUI backend. The service:

- accepts one HTTPS URL at `/frame-check/?url=...`;
- follows at most six HTTPS redirects on port 443;
- rejects loopback, private, link-local, reserved, credential-bearing, and non-HTTPS destinations;
- pins each connection to the validated public DNS answer while preserving TLS hostname verification;
- checks enforced `X-Frame-Options` and CSP `frame-ancestors` headers;
- treats Cloudflare Access hosted login redirects as browser-only because the hosted OTP step refuses framing;
- returns only `inline`, `browser`, or `unknown` JSON decisions;
- stores only a five-minute in-memory cache and emits no destination logs.

A private-live installation runs `checker.py` as a hardened user service on `127.0.0.1:8809` and publishes only `/frame-check/` with Tailscale Serve. Funnel must remain disabled. If the service is absent or returns `unknown`, HermesUI preserves the existing inline behavior and the bridge retains its manual `Open in browser` escape hatch.

Browser behavior cannot be inferred perfectly: cross-origin iframe success and browser refusal intentionally expose the same parent-page signals. This checker handles deterministic response-header blocks and known Access redirects without stripping destination security headers or creating a privileged browser proxy.
