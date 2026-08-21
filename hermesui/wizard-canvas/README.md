# Wizard Canvas

This downstream-only frontend package builds the self-hosted Excalidraw canvas embedded by HermesUI. The generated bundle and fonts live in `static/wizard-canvas/`; `node_modules/` and `.build-public/` are local build inputs only.

Build with `npm install && npm run build`. The canvas has one server-backed document at `/apps/api/wizard-canvas`; it does not connect to excalidraw.com, Excalidraw libraries, or collaboration services.
