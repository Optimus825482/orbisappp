const CACHE_NAME = "orbis-v5"; // v5: new_result.html async/await fix
const STATIC_ASSETS = [
  "/",
  "/static/css/tailwind.output.css",
  "/static/css/custom.css",
  "/static/js/app.js",
  "/manifest.json",
  "/static/ai-avatar-R.png",
  "/static/all-icons/Android/Icon-192.png",
  "/static/all-icons/Android/Icon-512.png",
];

// Install: cache static assets
self.addEventListener("install", (event) => {
  console.log("[SW] Installing v4...");
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.log("[SW] Cache addAll partial error:", err.message);
      });
    })
  );
  self.skipWaiting();
});

// Activate: clean old caches, take control
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME)
          .map((k) => caches.delete(k).then(() => console.log("[SW] Old cache deleted:", k)))
      )
    ).then(() => self.clients.claim())
  );
});

// Fetch: Network First for everything, cache fallback
self.addEventListener("fetch", (event) => {
  // Skip non-GET
  if (event.request.method !== "GET") return;

  const url = new URL(event.request.url);

  // Cross-origin: network only, don't cache
  if (url.origin !== self.location.origin) {
    return;
  }

  // API calls: network only (never cache)
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  // Static assets: network first, fallback to cache
  // html pages: network first (so new deployments show immediately)
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Cache successful responses
        if (response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => {
        // Offline: serve from cache
        return caches.match(event.request).then((cached) => {
          if (cached) return cached;
          // If html and not in cache, serve index.html (SPA fallback)
          if (url.pathname !== "/" && !url.pathname.match(/\.\w+$/)) {
            return caches.match("/");
          }
          return new Response("Offline", { status: 503 });
        });
      })
  );
});
