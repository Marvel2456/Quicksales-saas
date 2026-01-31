/**
 * Service Worker - Handles offline caching and request interception
 * 
 * This service worker intercepts network requests and serves cached
 * data when offline, enabling the app to work without internet connection.
 */

console.log('Service Worker script loaded');

const CACHE_NAME = 'quicksales-v1';
const CACHE_URLS = [
    '/',
    '/ims/',
    '/ims/store/',
    '/ims/cart/',
    '/ims/checkout/',
    '/static/assets/css/',
    '/static/assets/js/',
    '/static/assets/images/',
];

const API_ENDPOINTS_TO_CACHE = [
    '/ims/api/get-offline-data/'
];

/**
 * Install event - cache essential assets
 */
self.addEventListener('install', (event) => {
    console.log('🔧 Service Worker installing...');
    
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('Opened cache');
                // Try to cache files, but don't fail if they don't exist
                return Promise.all([
                    cache.add('/').catch(() => console.warn('Could not cache /')),
                    cache.add('/ims/').catch(() => console.warn('Could not cache /ims/')),
                    // Precache offline cart/checkout dependencies
                    cache.add('/static/assets/js/offline-manager.js').catch(() => console.warn('Could not cache offline-manager.js')),
                    cache.add('/static/assets/js/offline-cart-display.js').catch(() => console.warn('Could not cache offline-cart-display.js')),
                    cache.add('/static/assets/js/checkout.js').catch(() => console.warn('Could not cache checkout.js')),
                ]);
            })
            .catch((error) => {
                console.warn('Cache installation error:', error.message);
            })
            .then(() => {
                console.log('Service Worker install complete');
                self.skipWaiting();
            })
    );
});

/**
 * Activate event - clean up old caches
 */
self.addEventListener('activate', (event) => {
    console.log('Service Worker activating...');
    
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    
    self.clients.claim();
});

/**
 * Fetch event - serve from cache when offline
 */
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);
    
    console.log(`📡 Fetch: ${request.method} ${url.pathname}`);
    
    // Skip cross-origin requests
    if (url.origin !== location.origin) {
        console.log(`⏭️  Cross-origin, skipping`);
        return;
    }
    
    // PRIORITY: Handle cart and checkout pages - always return offline HTML
    if (url.pathname.includes('/cart/') || url.pathname.includes('/checkout/')) {
        console.log(`🛒 Cart/Checkout page detected`);
        event.respondWith(
            fetch(request)
                .then(response => {
                    console.log(`✅ Network succeeded for cart/checkout`);
                    return response;
                })
                .catch(() => {
                    console.log(`❌ Network failed, returning offline template`);
                    const isCheckout = url.pathname.includes('/checkout/');
                    return new Response(
                        `<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${isCheckout ? 'Checkout' : 'Cart'}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; background: white; }
        .alert { padding: 15px 20px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; margin-bottom: 20px; }
        .alert strong { color: #856404; }
        #offlineCartContainer { padding: 20px; text-align: center; }
        p { color: #999; }
    </style>
</head>
<body>
    <div class="container">
        <div class="alert">
            <strong>📡 Offline Mode</strong> - Your ${isCheckout ? 'checkout' : 'cart'} is loading from local storage...
        </div>
        <div id="offlineCartContainer">
            <p>Loading...</p>
        </div>
    </div>
    <script>
        console.log('✅ Service Worker returned offline ${isCheckout ? 'checkout' : 'cart'} page');
    </script>
    <script src="/static/assets/js/offline-manager.js"></script>
    <script src="/static/assets/js/offline-cart-display.js"></script>
    <script src="/static/assets/js/checkout.js"></script>
</body>
</html>`,
                        {
                            status: 200,
                            statusText: 'OK',
                            headers: { 'Content-Type': 'text/html; charset=utf-8' }
                        }
                    );
                })
        );
        return;
    }
    
    // Handle POST requests
    if (request.method === 'POST') {
        console.log(`📤 POST request`);
        event.respondWith(
            fetch(request).catch(() => {
                return new Response(
                    JSON.stringify({ offline: true, error: 'Queued for sync' }),
                    { status: 503, headers: { 'Content-Type': 'application/json' } }
                );
            })
        );
        return;
    }
    
    // For static assets, use cache-first strategy
    if (request.destination === 'style' || request.destination === 'script' || request.destination === 'image') {
        console.log(`📦 Static asset`);
        event.respondWith(
            caches.match(request)
                .then(cached => cached || fetch(request).then(response => {
                    if (response.ok) {
                        caches.open(CACHE_NAME).then(c => c.put(request, response.clone()));
                    }
                    return response;
                }))
                .catch(() => {
                    if (request.destination === 'image') {
                        return new Response('<svg></svg>', { headers: { 'Content-Type': 'image/svg+xml' } });
                    }
                    // For scripts/styles, return 200 with empty content instead of 503
                    // This prevents page breakage when scripts aren't in cache
                    if (request.destination === 'script') {
                        console.log(`⚠️  Script not in cache, returning empty: ${request.url}`);
                        return new Response('', { status: 200, headers: { 'Content-Type': 'application/javascript' } });
                    }
                    if (request.destination === 'style') {
                        console.log(`⚠️  Stylesheet not in cache, returning empty: ${request.url}`);
                        return new Response('', { status: 200, headers: { 'Content-Type': 'text/css' } });
                    }
                    return new Response('', { status: 503 });
                })
        );
        return;
    }
    
    // For HTML pages, network first
    console.log(`📄 HTML page`);
    event.respondWith(
        fetch(request)
            .then(response => {
                if (response.ok) {
                    caches.open(CACHE_NAME).then(c => c.put(request, response.clone()));
                }
                return response;
            })
            .catch(() => {
                console.log(`❌ Network failed for HTML page`);
                return caches.match(request).then(cached => cached || new Response('<h1>Offline</h1><p>Page not available</p>', { status: 503 }));
            })
    );
});

/**
 * Background Sync - automatically retry failed requests when online
 */
self.addEventListener('sync', (event) => {
    console.log('Background sync triggered:', event.tag);
    
    if (event.tag === 'sync-pending-sales') {
        event.waitUntil(
            syncPendingSales()
        );
    }
});

/**
 * Sync pending sales with the server
 */
async function syncPendingSales() {
    console.log('Starting background sync of pending sales...');
    
    // This will be called by the offline manager when connection is restored
    // The actual sync is handled in offline-manager.js
    
    return new Promise((resolve) => {
        setTimeout(resolve, 1000);
    });
}

/**
 * Message handler for communication with main thread
 */
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
    
    if (event.data && event.data.type === 'CACHE_DATA') {
        cacheOfflineData(event.data.data);
    }
});

/**
 * Cache offline data provided by the main thread
 */
async function cacheOfflineData(data) {
    const cache = await caches.open(CACHE_NAME);
    
    // Store data as JSON blobs
    const response = new Response(JSON.stringify(data), {
        headers: { 'Content-Type': 'application/json' }
    });
    
    await cache.put('/offline-data.json', response);
    console.log('✅ Offline data cached');
}

console.log('Service Worker loaded');
