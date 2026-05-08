// sw.js — Phase 138 Service Worker (오프라인 정적 자원 캐시)
const CACHE_NAME = 'cs-mobile-v1';
const STATIC_ASSETS = [
  '/seller/cs/mobile',
  '/seller/static/cs_mobile.js',
  '/seller/static/manifest.json',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  // Only cache static assets; pass through dynamic requests
  if (STATIC_ASSETS.some(a => url.pathname === a || url.pathname.startsWith('/seller/static/'))) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request))
    );
  }
});
