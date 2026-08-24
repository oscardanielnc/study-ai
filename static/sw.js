// Cachea SOLO assets inmutables. El HTML y la API van siempre a la red: un
// index.html cacheado servia una version vieja de la app para siempre, y los
// despliegues no llegaban nunca al movil.
const CACHE = "estudia-v6";
const ARMAZON = [
  "/styles.css?v=6", "/app.js?v=6",
  "/vendor/marked.min.js", "/vendor/katex.min.js",
  "/vendor/katex.min.css", "/vendor/auto-render.min.js",
  "/vendor/fonts.css",
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

  // El documento decide que version de la app se carga: red primero, y la
  // copia guardada solo si no hay conexion.
  if (e.request.mode === "navigate") {
    e.respondWith(
      fetch(e.request)
        .then((r) => {
          const copia = r.clone();
          caches.open(CACHE).then((c) => c.put("/", copia));
          return r;
        })
        .catch(() => caches.match("/"))
    );
    return;
  }

  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
