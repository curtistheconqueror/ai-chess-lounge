// Cache only this generic offline page. Never cache games, APIs, credentials or moves.
const CACHE = "chess-lounge-offline-v2";
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.add("/offline.html")).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys
    .filter(key => key.startsWith("chess-lounge-offline-") && key !== CACHE)
    .map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (event.request.mode !== "navigate" || event.request.method !== "GET" || url.origin !== self.location.origin
    || url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/")) return;
  // A proxy in front of a stopped or restarting server answers 502-504: show the
  // reconnect page instead of a bare gateway error.
  const offline = () => caches.match("/offline.html");
  event.respondWith(fetch(event.request, { cache: "no-store" })
    .then(response => ([502, 503, 504].includes(response.status) ? offline().then(page => page ?? response) : response))
    .catch(offline));
});
