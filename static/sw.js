// Cachea SOLO el armazon. El contenido (API) siempre va a la red:
// un resumen o un examen obsoletos serian peores que un error de conexion.
const CACHE = "estudia-v1";
const ARMAZON = [
  "/", "/index.html", "/styles.css", "/app.js",
  "/vendor/marked.min.js", "/vendor/katex.min.js",
  "/vendor/katex.min.css", "/vendor/auto-render.min.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ARMAZON)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((ks) =>
      Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return; // siempre red
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
