// sw.js — Phase 147 Service Worker (Proxy Commerce PWA)
const CACHE_NAME = 'proxy-commerce-v147';
const STATIC_ASSETS = [
  '/seller/dashboard',
  '/seller/static/seller.css',
  '/seller/static/seller.js',
  '/seller/static/manifest.json',
  '/seller/cs/mobile',
  '/seller/static/cs_mobile.js',
];
const OFFLINE_FALLBACK = '/seller/dashboard';

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
  // Only intercept same-origin requests
  if (url.origin !== self.location.origin) return;
  // Only cache static assets; pass through dynamic requests
  if (
    STATIC_ASSETS.some(a => url.pathname === a || url.pathname.startsWith('/seller/static/'))
  ) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request).catch(() =>
        caches.match(OFFLINE_FALLBACK)
      ))
    );
  }
  // Background fetch 비활성 (보안: 민감 데이터 캐시 방지)
});

// Web Push 알림 처리
self.addEventListener('push', event => {
  if (!event.data) return;
  let data = {};
  try { data = event.data.json(); } catch (e) { data = { title: '알림', body: event.data.text() }; }
  const title = data.title || 'Proxy Commerce';
  const options = {
    body: data.body || '',
    icon: data.icon || '/seller/static/icon-192.png',
    badge: '/seller/static/icon-192.png',
    data: { url: data.url || '/seller/dashboard' },
    requireInteraction: false,
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/seller/dashboard';
  event.waitUntil(clients.openWindow(url));
});
