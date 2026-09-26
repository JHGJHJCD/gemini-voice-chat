// sw.js — Service Worker: cache-first לקבצים סטטיים, רשת ישירה ל-WebSocket/API
// של Gemini (לא נוגעים בבקשות שאינן GET רגיל של הקבצים שלנו).

const CACHE_NAME = "gvc-cache-v1";
const PRECACHE = [
  "./",
  "./index.html",
  "./style.css",
  "./app.js",
  "./live.js",
  "./audio.js",
  "./media.js",
  "./storage.js",
  "./tools.js",
  "./worklets/mic-processor.js",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // רק בקשות GET מאותו מקור נכנסות ל-cache; הכל אחר (Gemini API/CDN) → רשת ישירה
  if (event.request.method !== "GET" || url.origin !== self.location.origin) return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request)
        .then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(() => cached);
    })
  );
});
