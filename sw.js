// Penyimpan offline sederhana: halaman dan data diambil dari internet dulu (selalu terbaru),
// bila gagal (tidak ada sinyal) memakai salinan terakhir. Ikon, huruf, dan pustaka grafik disimpan permanen.
const CACHE = "screener-v2";
self.addEventListener("install", e => { self.skipWaiting(); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const isStatic = /\/icons\//.test(url.pathname) || /fonts\.(googleapis|gstatic)\.com|unpkg\.com/.test(url.host);
  if (isStatic) {
    e.respondWith(caches.open(CACHE).then(c => c.match(req).then(hit => hit || fetch(req).then(res => { if (res.ok || res.type === "opaque") c.put(req, res.clone()); return res; }))));
    return;
  }
  if (url.origin !== location.origin) return;
  e.respondWith(fetch(req).then(res => {
    if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(url.origin + url.pathname, copy)); } // satu salinan per file (abaikan ?t=)
    return res;
  }).catch(() => caches.match(req, {ignoreSearch: true}).then(hit => hit || caches.match(new URL("./", self.registration.scope).href))));
});
