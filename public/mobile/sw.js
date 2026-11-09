const CACHE = "prevclima-mobile-v8";
const SHELL = [
  "/mobile/",
  "/mobile/inicio.html",
  "/mobile/mobile.css",
  "/mobile/mobile.js",
  "/mobile/mobile-home.js",
  "/mobile/icon.svg",
  "/assets/js/api.js"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key.startsWith("prevclima-mobile-") && key !== CACHE).map((key) => caches.delete(key)))));
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (new URL(event.request.url).origin !== self.location.origin) return;
  if (event.request.method !== "GET" || new URL(event.request.url).pathname.startsWith("/api/")) return;
  event.respondWith(fetch(event.request).then((response) => {
    const copy = response.clone();
    if (response.ok) event.waitUntil(caches.open(CACHE).then((cache) => cache.put(event.request, copy)));
    return response;
  }).catch(() => caches.match(event.request).then((cached) => cached || new Response("Sem conexão. Reconecte e tente novamente.", { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } }))));
});
