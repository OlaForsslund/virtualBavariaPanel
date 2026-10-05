// Phone-only shell cache; bump CACHE when this logic changes.
const CACHE = 'vbp-shell-v4';
const SHELL = [
  '/', '/power-diagram.js', '/manifest.json',
  '/font/DejaVuSans.ttf', '/font/DejaVuSans-Bold.ttf',
  '/favicon-16x16.png', '/favicon-32x32.png', '/apple-touch-icon.png',
  '/android-chrome-192x192.png', '/android-chrome-512x512.png'
];

self.addEventListener('install', event => {
  // Per-file so one missing file can't fail the install.
  event.waitUntil(
    caches.open(CACHE)
      .then(cache => Promise.all(SHELL.map(path => cache.add(path).catch(() => {}))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(names => Promise.all(names.filter(n => n !== CACHE).map(n => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;
  // The page itself is cached as '/', whatever its query (mfd_name etc.).
  const key = (url.pathname === '/' || url.pathname === '/index.html') ? '/' : url.pathname;
  if (!SHELL.includes(key)) return;
  // hardReload() adds ?_r= and must reach the network.
  const refresh = fetch(req).then(res => {
    if (res.ok) {
      const copy = res.clone();
      caches.open(CACHE).then(cache => cache.put(key, copy));
    }
    return res;
  });
  if (url.searchParams.has('_r')) { event.respondWith(refresh); return; }
  event.respondWith(caches.match(key).then(hit => {
    if (hit) { refresh.catch(() => {}); return hit; }
    return refresh;
  }));
});
