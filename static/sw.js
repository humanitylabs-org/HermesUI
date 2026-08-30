/**
 * Hermes WebUI Service Worker
 * Minimal PWA service worker — enables "Add to Home Screen".
 * No offline caching of API responses (the UI requires a live backend).
 * Caches only static shell assets so the app shell loads fast on repeat visits.
 */

// Cache version is injected by the server at request time (routes.py /sw.js handler).
// Bumps automatically whenever the git commit changes — no manual edits needed.
// HermesUI frontend delivery marker: wizard-canvas-v8. This intentionally
// changes the worker bytes so hot frontend deployments refresh an existing
// process's shell cache without interrupting active agent runs. The private-app
// rail marker keeps the visible selector limited to installed private apps.
// performance-cache-v1 serves immutable versioned shell bytes immediately and
// refreshes the same exact URL in the background.
const CACHE_NAME = 'hermes-shell-__WEBUI_VERSION__';

// Static assets that form the app shell.
//
// Versioned assets (CSS + JS) include `?v=__WEBUI_VERSION__` to match the
// query string the page sends — see index.html. Without the version query
// here, every cache lookup against `?v=...` URLs would miss and fall through
// to network, defeating the pre-cache.
//
// Do not pre-cache './' or login assets here: under password auth they can be
// either the authenticated app shell or login code, and stale cached responses
// can make valid password submits fail until the user clears browser cache.
// Navigations populate './' only after a successful non-redirect network load.
const VQ = '?v=__WEBUI_VERSION__';
const SHELL_ASSETS = [
  './static/style.css' + VQ + '&overlay=wizard-canvas-v8&cron-notifications=v9&high-signal-model=v2&high-signal-layout=v1&high-signal-mode=v1&shell-theme=v1&session-status-groups=v1&private-app-rail=v1&new-session-divider=v2&opus-polish=v1&new-session-emphasis=v1&high-signal-toggle=v1&mobile-session-home=v1&notification-operations=v3&mobile-rail-right=v1&rail-selection-ring=v1&human-cron=v1&active-frequency=v1&scheduled-dashboard=v1&mobile-utility-menu=v1&mobile-bottom-menu=v1&mobile-collapsible-rail=v1&mobile-modern-nav=v1&notification-hierarchy=v1&notification-reply-indicators=v1&mobile-folder-dock=v2&folder-pill-colors=v1&mobile-tabs-removed=v1&mobile-toggle-switches=v1&voice-notes=v1&mobile-folder-quiet=v2&mobile-titlebar=v1&mobile-layer-nav=v7',
  './static/pwa-startup.js' + VQ,
  './static/boot.js' + VQ + '&tab-polish=v1&mobile-tabs-removed=v1&mobile-back-instant=v1',
  './static/assistant_turn_anchors.js' + VQ,
  './static/ui.js' + VQ + '&tab-polish=v1&recovery-filter=v2&background-resume=v1&classic-duration=v1&voice-notes=v1',
  './static/messages.js' + VQ + '&tab-polish=v1&recovery-filter=v2',
  './static/sessions.js' + VQ + '&tab-polish=v1&status-groups=v1&new-session-divider=v2&status-indicators=v1&blank-draft-working=v1&contained-cron-replies=v1&hidden-cron-project=v1&performance-cache=v1&mobile-folder-dock=v2&folder-pill-colors=v1&done-first=v1&sidebar-order=v2&mobile-tabs-removed=v1&mobile-back-loading=v3',
  './static/tailnet-app-rail.js' + VQ + '&overlay=wizard-canvas-v8&bookmark-fallback=v5&bookmark-sync=v1&cron-notifications=v8&shell-theme=v1&private-only=v1&mobile-session-home=v1&cron-operations=v3&mobile-rail-right=v1&human-cron=v1&active-frequency=v1&scheduled-dashboard=v1&silent-notifications=v1&mobile-utility-menu=v1&mobile-bottom-menu=v1&mobile-collapsible-rail=v1&performance-cache=v1&notification-stream=v1&notification-hierarchy=v1&notification-reply-indicators=v1&mobile-toggle-switches=v1&mobile-layer-nav=v5',
  './static/tailnet-app-manager.js' + VQ + '&cron-notifications=v3&semantic-icons=v1&mobile-layer-nav=v3&cloudflare-paths=v1',
  './static/mobile-layer-navigation.js' + VQ + '&mobile-layer-nav=v8',
  './static/panels.js' + VQ + '&cron-notifications=v3&high-signal-model=v1&cron-modal=v1&human-cron=v1&scheduled-dashboard=v1',
  './static/commands.js' + VQ,
  './static/icons.js' + VQ,
  './static/i18n.js' + VQ + '&human-cron=v1',
  './static/workspace.js' + VQ,
  './static/terminal.js' + VQ,
  './static/onboarding.js' + VQ,
  './static/session-dashboard.js' + VQ + '&tab-polish=v1&high-signal-model=v6&high-signal-history=v1&background-resume=v1&mode-rail=v1&summary-trust=v1&high-signal-toggle=v1',
  './static/vendor/smd.min.js' + VQ,
  './static/vendor/katex/0.16.22/katex.min.css' + VQ,
  './static/vendor/katex/0.16.22/katex.min.js' + VQ,
  './static/wizard-hat-32.png',
  './static/wizard-hat-192.png',
  './manifest.json',
];

function deleteOldShellCaches() {
  return caches.keys().then((keys) =>
    Promise.all(
      keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
    )
  );
}

// Install: prune old shell caches first, then pre-cache the app shell. Doing
// this before caches.open(CACHE_NAME) avoids a temporary double-cache window on
// quota-sensitive browsers during frequent version bumps.
self.addEventListener('install', (event) => {
  event.waitUntil(
    deleteOldShellCaches().then(() =>
      caches.open(CACHE_NAME).then((cache) => {
        return cache.addAll(SHELL_ASSETS).catch((err) => {
          // Non-fatal: if any asset fails, still activate
          console.warn('[sw] Shell pre-cache partial failure:', err);
        });
      })
    )
  );
  self.skipWaiting();
});

// Activate: keep the old-cache cleanup as a safety net in case install was
// interrupted or an older worker was already waiting.
self.addEventListener('activate', (event) => {
  event.waitUntil(deleteOldShellCaches());
  self.clients.claim();
});

// Fetch strategy:
// - API calls (/api/*, /stream) → always network (never cache)
// - Login assets → always network (never cache stale auth code)
// - Page navigations → network-first so auth redirects/cookies are honored
// - Versioned shell assets → cached immediately, revalidated in background
// - Everything else → network-only
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Never intercept cross-origin requests
  if (url.origin !== self.location.origin) return;

  // Never intercept the service worker script itself. Returning a cached sw.js
  // prevents the browser from seeing a new cache version after local patches.
  if (url.pathname.endsWith('/sw.js')) return;

  // Login assets must always hit the network. Older login.js builds have had
  // subpath-sensitive auth POST paths; if the service worker caches one, the
  // password can keep failing until the user manually clears browser cache.
  if (
    url.pathname.endsWith('/login') ||
    url.pathname.endsWith('/static/login.js')
  ) {
    return;
  }

  // API and streaming endpoints — always go to network.
  // The WebUI may be mounted under a subpath such as /hermes/, so API
  // requests can look like /hermes/api/sessions rather than /api/sessions.
  if (
    url.pathname.startsWith('/api/') ||
    url.pathname.includes('/api/') ||
    url.pathname.includes('/stream') ||
    url.pathname.startsWith('/health') ||
    url.pathname.includes('/health')
  ) {
    return; // let browser handle normally
  }

  // Page navigations must be network-first. A stale cached './' response can
  // otherwise hide the server's 302-to-login after auth expiry, or ignore a
  // freshly set login cookie until the user manually refreshes.
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(new Request(event.request, { cache: 'no-store' })).then((response) => {
        if (
          event.request.method === 'GET' &&
          response.status === 200 &&
          !response.redirected
        ) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put('./', clone));
        }
        return response;
      }).catch(() => {
        return caches.match('./').then((cached) => cached || new Response(
          '<html><body style="font-family:sans-serif;padding:2rem;background:#1a1a1a;color:#ccc">' +
          '<h2>You are offline</h2>' +
          '<p>Hermes requires a server connection. Please check your network and try again.</p>' +
          '</body></html>',
          { headers: { 'Content-Type': 'text/html' } }
        ));
      })
    );
    return;
  }

  // Only explicit shell assets are cached. Everything else should hit the
  // network so stale one-off files (especially auth/login scripts) do not get
  // trapped in CacheStorage until a manual cache clear.
  const scopePath = new URL(self.registration.scope).pathname;
  const relPath = url.pathname.startsWith(scopePath)
    ? url.pathname.slice(scopePath.length)
    : url.pathname.replace(/^\/+/, '');
  const shellPath = './' + relPath.replace(/^\/+/, '') + url.search;
  if (!SHELL_ASSETS.includes(shellPath)) return;

  // Shell assets: network-first with cache fallback was the previous policy.
  // stale-while-revalidate is safe here because every JS/CSS request carries
  // the git version in its exact URL, so a deployment naturally misses the old
  // cache. Repeat visits get current cached bytes without a network round-trip,
  // while the same URL refreshes in the background for local same-version fixes.
  const refresh = fetch(new Request(event.request, { cache: 'no-store' })).then((response) => {
    if (event.request.method === 'GET' && response.status === 200) {
      const clone = response.clone();
      caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
    }
    return response;
  }).catch(() => caches.match(event.request).then((cached) => (
    cached || Promise.reject(new Error('shell unavailable'))
  )));
  event.waitUntil(refresh.then(() => undefined, () => undefined));
  event.respondWith(
    caches.match(event.request).then((cached) => cached || refresh).catch(() => new Response('Offline', {
      status: 503,
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    }))
  );
});


self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const rawUrl = (event.notification.data && event.notification.data.url) || './';
  const targetUrl = new URL(rawUrl, self.registration.scope || './').href;
  const targetPath = new URL(targetUrl).pathname;
  const samePath = (clientUrl) => {
    try { return new URL(clientUrl).pathname === targetPath; } catch (_e) { return false; }
  };
  const sameOrigin = (clientUrl) => {
    try { return new URL(clientUrl).origin === self.location.origin; } catch (_e) { return false; }
  };
  event.waitUntil(
    self.clients.matchAll({type: 'window', includeUncontrolled: true}).then((clientList) => {
      // Match on pathname, not the full href: _sessionUrlForSid copies the
      // current page's query string + hash into the deep link, so an open tab
      // already on /session/<sid> would fail an exact-href match and spawn a
      // duplicate window.
      const targetClient = clientList.find((client) => samePath(client.url) && 'focus' in client);
      if (targetClient) return targetClient.focus();

      const openNotificationWindow = () => (
        self.clients.openWindow ? self.clients.openWindow(targetUrl) : undefined
      );
      const focusableClient = clientList.find((client) => sameOrigin(client.url) && 'focus' in client && 'navigate' in client);
      if (focusableClient && 'navigate' in focusableClient) {
        return focusableClient.navigate(targetUrl)
          .then((client) => (client && 'focus' in client ? client.focus() : focusableClient.focus()))
          .catch(() => focusableClient.focus());
      }
      return openNotificationWindow();
    })
  );
});
