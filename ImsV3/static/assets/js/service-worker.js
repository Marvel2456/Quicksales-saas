/**
 * Service Worker for Quicksales Store Offline Mode
 * Handles asset caching, request interception, and HTML fallbacks.
 */

const CACHE_NAME = 'quicksales-offline-v3';

function getBranchIdFromPath(pathname) {
    const match = pathname.match(/\/(?:store|cart|checkout|completed|products|inventorys|branchdash|invoices|sales)\/([a-f0-9-]+)/i);
    return match ? match[1] : '';
}

const CACHE_ASSETS = [
    '/static/assets/css/portal.css',
    '/static/assets/css/bootstrap.min.css',
    '/static/assets/plugins/fontawesome/js/all.min.js',
    '/static/assets/plugins/bootstrap/js/bootstrap.min.js',
    '/static/assets/js/jQuery%203.6.1.min.js',
    '/static/assets/js/jquery-3.4.1.js',
    '/static/assets/js/offline-manager.js',
    '/static/assets/js/offline-cart-display.js',
    '/static/assets/images/user_thumb.png',
    // NOTE: mq.png is intentionally NOT cached here.
    // It is used as the network health-check target by offline-manager.js.
    // Caching it would make pings succeed even when truly offline.
];

self.addEventListener('install', (event) => {
    console.log('🔧 SW: Installing and caching shell assets...');
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(CACHE_ASSETS).catch(err => {
                console.warn('🔧 SW: Warning caching assets during install:', err);
            });
        }).then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    console.log('🔧 SW: Activating and clearing old caches...');
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.map((key) => {
                    if (key !== CACHE_NAME) {
                        return caches.delete(key);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Only handle same-origin requests
    if (url.origin !== location.origin) {
        return;
    }

    // Never intercept HEAD requests — they are used as network health pings
    // and MUST hit the real network to accurately detect connectivity.
    if (request.method === 'HEAD') {
        return;
    }

    // Never intercept POST requests — let them fail naturally when offline
    if (request.method === 'POST') {
        return;
    }

    // Intercept cart and checkout page navigations to render offline fallback
    if (url.pathname.includes('/cart/') || url.pathname.includes('/checkout/')) {
        event.respondWith(
            fetch(request).catch(() => {
                console.log('📡 SW: Offline detected for page:', url.pathname);
                const isCheckout = url.pathname.includes('/checkout/');
                return new Response(
                    `<!DOCTYPE html>
                    <html lang="en">
                    <head>
                        <meta charset="UTF-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <title>${isCheckout ? 'Offline Checkout' : 'Offline Cart'}</title>
                        <link rel="stylesheet" href="/static/assets/css/portal.css">
                        <link rel="stylesheet" href="/static/assets/css/bootstrap.min.css">
                        <script defer src="/static/assets/plugins/fontawesome/js/all.min.js"><\/script>
                        <style>
                            body { background-color: #f5f6f8; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
                            .offline-container { max-width: 800px; margin: 50px auto; padding: 20px; }
                            .status-banner { padding: 12px; border-radius: 8px; font-weight: 500; margin-bottom: 25px; }
                            @media print {
                                body { background-color: #fff !important; }
                                .offline-container { margin: 0 !important; padding: 0 !important; max-width: 100% !important; }
                                .d-print-none { display: none !important; }
                                .card { border: 0 !important; box-shadow: none !important; padding: 0 !important; }
                            }
                        </style>
                    </head>
                    <body>
                        <header class="app-header fixed-top d-print-none" style="background: #02296e; height: 56px; display: flex; align-items: center; padding-left: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.1);">
                            <a href="" style="color: white; font-weight: bold; text-decoration: none; display: flex; align-items: center;">
                                <span style="font-size: 1.2rem; letter-spacing: 0.5px;">QUICKSALES</span>
                                <span class="badge bg-warning ms-2" style="font-size: 0.7rem; font-weight: 600;">OFFLINE</span>
                            </a>
                        </header>
                        <div class="offline-container pt-5">
                            <div class="status-banner d-print-none bg-warning-subtle border border-warning text-warning-emphasis d-flex align-items-center justify-content-between">
                                <span><i class="fa-solid fa-signal-vertical-slash me-2"></i> <strong>Offline Store POS</strong>: Transactions are queued locally and will sync when network returns.</span>
                                <span class="badge bg-warning text-dark">Local Mode</span>
                            </div>
                            
                            <!-- Multiple Sales Management Section for Offline Mode -->
                            <div class="card border-0 shadow-sm p-3 mb-4 d-print-none" id="offlineSalesCard" style="display: none;">
                                <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
                                    <div>
                                        <h6 class="mb-2"><strong>Open Sales Sessions</strong></h6>
                                        <div id="offlineSalesGroup" class="btn-group" role="group">
                                            <!-- Buttons dynamically loaded -->
                                        </div>
                                    </div>
                                    <div id="offlineButtons">
                                        <button class="btn btn-success btn-sm" id="offlineNewSaleBtn">
                                            <i class="fa-solid fa-plus me-1"></i> New Sale
                                        </button>
                                        <button class="btn btn-danger btn-sm" id="offlineCancelBtn">
                                            <i class="fa-solid fa-times me-1"></i> Cancel Current
                                        </button>
                                    </div>
                                </div>
                            </div>
                            
                            <div id="offlineContentContainer">
                                <div class="text-center py-5">
                                    <div class="spinner-border text-primary" role="status"></div>
                                    <p class="mt-3 text-muted">Initializing offline application database...</p>
                                </div>
                            </div>
                        </div>
                        
                        <script>
                            // Pass contextual information to offline JS displays
                            window.IS_CHECKOUT_PAGE = ${isCheckout};
                            window.BRANCH_ID = "${getBranchIdFromPath(url.pathname)}";
                        <\/script>
                        <script src="/static/assets/js/offline-manager.js"><\/script>
                        <script src="/static/assets/js/offline-cart-display.js"><\/script>
                    </body>
                    </html>`,
                    {
                        status: 200,
                        headers: { 'Content-Type': 'text/html' }
                    }
                );
            })
        );
        return;
    }

    // Cache-first for static assets (CSS, JS, images in our shell list)
    if (CACHE_ASSETS.some(asset => url.pathname === asset || url.pathname === decodeURIComponent(asset))) {
        event.respondWith(
            caches.match(request).then((cachedResponse) => {
                return cachedResponse || fetch(request).then((networkResponse) => {
                    if (networkResponse.ok) {
                        const responseClone = networkResponse.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone));
                    }
                    return networkResponse;
                });
            })
        );
        return;
    }

    // Cache successful GET requests for media files (logos, etc.)
    if (request.method === 'GET' && url.pathname.startsWith('/media/')) {
        event.respondWith(
            caches.match(request).then((cachedResponse) => {
                return cachedResponse || fetch(request).then((networkResponse) => {
                    if (networkResponse.ok) {
                        const responseClone = networkResponse.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone));
                    }
                    return networkResponse;
                });
            })
        );
        return;
    }

    // Network first for HTML page navigations only (not API calls or other fetches)
    const acceptHeader = request.headers.get('accept') || '';
    if (request.method === 'GET' && acceptHeader.includes('text/html')) {
        event.respondWith(
            fetch(request).then((response) => {
                // Cache successful app HTML page loads for offline rendering
                const isAppPage = url.pathname.includes('/ims/') || 
                                  url.pathname.includes('/account/') || 
                                  url.pathname === '/';
                const isExcluded = url.pathname.includes('/logout/') || 
                                   url.pathname.includes('/admin/') || 
                                   url.pathname.includes('__debug__');
                
                if (response.ok && isAppPage && !isExcluded) {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone));
                }
                return response;
            }).catch(() => {
                return caches.match(request).then((cachedResponse) => {
                    return cachedResponse || new Response(
                        `<!DOCTYPE html><html><body><div style="padding: 50px; text-align: center;"><h3>Offline</h3><p>This page is not cached. Please visit it once online.</p><a href="javascript:history.back()">Go Back</a></div></body></html>`,
                        { status: 503, headers: { 'Content-Type': 'text/html' } }
                    );
                });
            })
        );
    }
});
