// Bulkognize Service Worker - basic offline shell caching

var CACHE_NAME = "bulkognize-v1";
var SHELL_URLS = [
    "/",
    "/static/style.css",
    "/static/app.js",
    "/static/manifest.json",
    "/static/icon-192.png",
    "/static/icon-512.png"
];

// Install: cache the app shell
self.addEventListener("install", function (event) {
    event.waitUntil(
        caches.open(CACHE_NAME).then(function (cache) {
            return cache.addAll(SHELL_URLS);
        })
    );
    self.skipWaiting();
});

// Activate: clean up old caches
self.addEventListener("activate", function (event) {
    event.waitUntil(
        caches.keys().then(function (names) {
            return Promise.all(
                names.filter(function (name) {
                    return name !== CACHE_NAME;
                }).map(function (name) {
                    return caches.delete(name);
                })
            );
        })
    );
    self.clients.claim();
});

// Fetch: network first for API calls, cache first for app shell
self.addEventListener("fetch", function (event) {
    var url = new URL(event.request.url);

    // Never cache API calls or POST requests
    if (event.request.method !== "GET" || url.pathname.startsWith("/api/")) {
        return;
    }

    event.respondWith(
        fetch(event.request)
            .then(function (response) {
                // Update cache with fresh version
                var clone = response.clone();
                caches.open(CACHE_NAME).then(function (cache) {
                    cache.put(event.request, clone);
                });
                return response;
            })
            .catch(function () {
                // Offline: serve from cache
                return caches.match(event.request);
            })
    );
});
