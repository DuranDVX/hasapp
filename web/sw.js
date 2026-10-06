// SiteSafe service worker: the app shell works with no signal.
// App files: network first (a deploy shows at once), cache after 3 s or offline.
// API calls are never cached here; the app keeps its own offline data in IndexedDB.
const CACHE = "sitesafe-v3";
const SHELL = ["/app.html", "/style.css", "/idb.js", "/sign.js", "/app.js", "/forms.js", "/manage.js", "/board.js", "/registers.js", "/consultant.js",
  "/manifest.webmanifest", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", (e) => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  if (url.pathname.startsWith("/p/")) return;   // QR redirects
  e.respondWith((async () => {
    const key = new Request(url.origin + (url.pathname === "/" ? "/app.html" : url.pathname));
    const cached = () => caches.match(key);
    const net = fetch(req, { cache: "no-cache" }).then((r) => {
      if (r.ok && r.type === "basic") { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(key, copy)); }
      return r;
    });
    const slow = new Promise((res) => setTimeout(res, 3000)).then(cached);
    try {
      const first = await Promise.race([net, slow]);
      return first || await net;
    } catch {
      return (await cached()) || (await caches.match("/app.html")) || Response.error();
    }
  })());
});
