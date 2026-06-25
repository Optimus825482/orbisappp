const CACHE_NAME = "orbis-v7"; // v7: SW sadece statik dosyalar — HTML'i CACHE'LEME
const STATIC_ASSETS = [
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
  console.log("[SW] Installing v7...");
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

  // HTML pages: NETWORK ONLY — asla cache'leme ki deploy hemen görünsün
  if (
    event.request.headers.get("accept") &&
    event.request.headers.get("accept").includes("text/html")
  ) {
    event.respondWith(
      fetch(event.request).catch(
        () => new Response("Offline", { status: 503 })
      )
    );
    return;
  }

  // Static assets: network first, fallback to cache
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
          return new Response("Offline", { status: 503 });
        });
      })
  );
});
