const CACHE_VERSION = "reco3-pwa-v2";
const APP_SHELL = [
  "/r3",
  "/static/base.css",
  "/static/reco3.css",
  "/static/reco3.js",
  "/static/manifest.webmanifest"
];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_VERSION);
    await cache.addAll(APP_SHELL);
    self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => (k !== CACHE_VERSION ? caches.delete(k) : Promise.resolve())));
    self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  if (url.pathname.startsWith("/api/")) {
    return; // never cache API responses
  }

  event.respondWith((async () => {
    try {
      const fresh = await fetch(event.request);
      const cache = await caches.open(CACHE_VERSION);
      cache.put(event.request, fresh.clone());
      return fresh;
    } catch (e) {
      const cached = await caches.match(event.request);
      return cached || new Response("Offline", { status: 503, headers: { "Content-Type": "text/plain" } });
    }
  })());
});
