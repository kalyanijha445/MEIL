// static/sw.js

const CACHE_NAME = 'meil-safety-portal-v1';
// List of files to cache when the service worker is installed.
const urlsToCache = [
  '/',
  '/static/images/icon-192.png',
  '/static/images/icon-512.png',
  // You can add more URLs here, like CSS or JS files, if you have them.
  // For example: '/static/style.css'
];

// Install event: open a cache and add the assets to it
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Opened cache');
        return cache.addAll(urlsToCache);
      })
  );
});

// Fetch event: serve cached content when offline
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Cache hit - return response from the cache
        if (response) {
          return response;
        }
        // Not in cache - fetch from network
        return fetch(event.request);
      }
    )
  );
});