// sw.js — Phase 147 Service Worker (고가브릿지 PWA) · v39-M 앱셸 캐시(정직: 동적 데이터 미캐시)
const CACHE_NAME = 'gogabridj-v39';
// 앱 셸(정적 자산)만 캐시 — 대시보드/주문 등 동적 데이터 페이지는 캐시하지 않는다(스테일 가짜 데이터 방지).
const STATIC_ASSETS = [
  '/seller/static/seller.css',
  '/seller/static/seller.js',
  '/seller/static/cs_mobile.js',
  '/seller/static/manifest.webmanifest',
  '/seller/static/offline.html',
];
// 오프라인 폴백 = 정직한 '오프라인' 안내 페이지(저장 데이터 미노출).
const OFFLINE_FALLBACK = '/seller/static/offline.html';

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
  // 동일 출처만 가로챈다
  if (url.origin !== self.location.origin) return;

  // 동적 페이지 네비게이션: 항상 네트워크 우선(실시간 데이터). 오프라인이면 정직한 오프라인 페이지.
  //   캐시에서 동적 데이터를 되돌려주지 않는다(스테일/가짜 데이터 방지).
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(OFFLINE_FALLBACK))
    );
    return;
  }

  // 정적 앱셸 자산만 캐시 우선(빠른 로드). 동적 API/데이터는 통과(캐시 안 함).
  if (url.pathname.startsWith('/seller/static/')) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request).catch(() =>
        caches.match(OFFLINE_FALLBACK)
      ))
    );
  }
  // 그 외(동적 요청)는 가로채지 않음 — 항상 네트워크(민감 데이터 캐시 방지).
});

// Web Push 알림 처리
self.addEventListener('push', event => {
  if (!event.data) return;
  let data = {};
  try { data = event.data.json(); } catch (e) { data = { title: '알림', body: event.data.text() }; }
  const title = data.title || 'gogabridj';
  const options = {
    body: data.body || '',
    icon: data.icon || undefined,
    badge: undefined,
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
