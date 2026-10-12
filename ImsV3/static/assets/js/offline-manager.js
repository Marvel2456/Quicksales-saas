/**
 * Quicksales Offline POS Manager
 * Handles IndexedDB database initialization, network connectivity checks,
 * local catalog caching, and background sync logic.
 */

class OfflineManager {
    constructor() {
        this.dbName = 'QuicksalesOfflineDB';
        this.dbVersion = 2;
        this.db = null;
        this.branchId = this.detectBranchId();
        const savedState = sessionStorage.getItem('quicksales_network_state');
        this.isOnline = savedState ? (savedState === 'online') : navigator.onLine;
        this.syncInProgress = false;
        
        this.init();
    }

    async init() {
        try {
            await this.openDatabase();
            this.setupNetworkMonitoring();
            this.flushQueuedNotices();
            
            if (this.branchId) {
                // If online, refresh local product cache and trigger background sync
                if (this.isOnline) {
                    // Order matters: push offline work first, then pull fresh server state
                    await this.syncPendingSales();
                    await this.syncOpenCarts();
                    await this.mirrorOnlineCarts();
                    await this.refreshLocalCatalog();
                    this.triggerActivePrecaching().catch(err => {
                        console.error('📡 OfflineManager: Active pre-caching failed:', err);
                    });
                } else {
                    const cart = await this.getActiveOfflineSale();
                    this.updateCartBadgeCount(cart);
                }
                
                // Safety net: keep the local mirror of the online cart fresh so a
                // sudden network drop continues from the latest state.
                setInterval(() => {
                    if (this.isOnline) this.mirrorOnlineCarts();
                }, 30000);
                
                this.setupAddToCartInterception();
                
                if (window.location.pathname.includes('/store/')) {
                    this.setupOfflineStoreInterception();
                }
            }
            
            console.log('✅ OfflineManager: Initialization complete.');
        } catch (error) {
            console.error('❌ OfflineManager: Initialization failed:', error);
        }
    }

    detectBranchId() {
        // Can be set on window context by template, or parsed from URL path
        if (window.BRANCH_ID) return window.BRANCH_ID;
        
        const match = window.location.pathname.match(/\/(?:store|cart|checkout|completed|products|inventorys|branchdash|invoices|sales)\/([a-f0-9-]+)/i);
        return match ? match[1] : null;
    }

    async triggerActivePrecaching() {
        if (!this.isOnline || !this.branchId) return;
        
        console.log('📡 OfflineManager: Starting active pre-caching for branch:', this.branchId);
        
        const urlsToPrecache = [
            `/ims/store/${this.branchId}/`,
            `/ims/cart/${this.branchId}/`,
            `/ims/checkout/${this.branchId}/`,
            `/ims/products/${this.branchId}/`,
            `/ims/inventorys/${this.branchId}/`
        ];
        
        for (const url of urlsToPrecache) {
            try {
                // Fetch in the background with Accept: text/html to trigger SW caching
                await fetch(url, { 
                    headers: { 'Accept': 'text/html' },
                    cache: 'no-cache' 
                });
                console.log(`📡 OfflineManager: Active pre-cached path: ${url}`);
            } catch (e) {
                console.warn(`📡 OfflineManager: Failed to active pre-cache path: ${url}`, e);
            }
        }
        console.log('📡 OfflineManager: Active pre-caching complete.');
    }

    openDatabase() {
        return new Promise((resolve, reject) => {
            let settled = false;
            const request = indexedDB.open(this.dbName, this.dbVersion);
            
            request.onerror = (e) => {
                if (!settled) { settled = true; reject(e.target.error); }
            };
            request.onsuccess = (e) => {
                if (!settled) {
                    settled = true;
                    this.db = e.target.result;
                    resolve(this.db);
                }
            };
            
            // Handle the case where another tab has the DB open at an older version
            request.onblocked = () => {
                console.warn('⚠️ OfflineManager: IndexedDB open blocked by another connection.');
                if (!settled) {
                    settled = true;
                    reject(new Error('IndexedDB blocked'));
                }
            };
            
            request.onupgradeneeded = (e) => {
                const db = e.target.result;
                // Catalog cache: store details of branch inventory
                if (!db.objectStoreNames.contains('catalog')) {
                    db.createObjectStore('catalog', { keyPath: 'id' });
                }
                // Offline Cart: key is branch_id, stores items array
                if (!db.objectStoreNames.contains('offline_cart')) {
                    db.createObjectStore('offline_cart', { keyPath: 'branch_id' });
                }
                // Pending sales queue to sync back to cloud
                if (!db.objectStoreNames.contains('pending_sales')) {
                    db.createObjectStore('pending_sales', { keyPath: 'tempId' });
                }
                // Metadata configuration cache
                if (!db.objectStoreNames.contains('metadata')) {
                    db.createObjectStore('metadata', { keyPath: 'key' });
                }
                // Offline multiple open sales sessions
                if (!db.objectStoreNames.contains('offline_sales')) {
                    db.createObjectStore('offline_sales', { keyPath: 'id' });
                }
            };
            
            // Safety timeout: if IDB doesn't respond in 5 seconds, reject
            setTimeout(() => {
                if (!settled) {
                    settled = true;
                    reject(new Error('IndexedDB open timed out'));
                }
            }, 5000);
        });
    }

    setupNetworkMonitoring() {
        // Listen to native online/offline events
        window.addEventListener('online', () => this.handleNetworkChange(true));
        window.addEventListener('offline', () => this.handleNetworkChange(false));
        
        // Initial badge update
        this.updateNetworkBadge();

        // Perform an immediate connectivity check
        this.checkActualConnectivity();

        // Perform periodic pings every 5 seconds to double-check actual connectivity
        setInterval(() => this.checkActualConnectivity(), 5000);
    }

    async checkActualConnectivity() {
        if (navigator.onLine) {
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 4000);
                // Hit a lightweight static file or URL to verify backend access
                const response = await fetch('/static/assets/images/mq.png', { 
                    method: 'HEAD', 
                    signal: controller.signal,
                    cache: 'no-store'
                });
                clearTimeout(timeoutId);
                
                const onlineNow = response.ok;
                if (onlineNow !== this.isOnline) {
                    this.handleNetworkChange(onlineNow);
                }
            } catch (e) {
                if (this.isOnline) {
                    this.handleNetworkChange(false);
                }
            }
        } else if (this.isOnline) {
            this.handleNetworkChange(false);
        }
    }

    async handleNetworkChange(isOnline) {
        this.isOnline = isOnline;
        sessionStorage.setItem('quicksales_network_state', isOnline ? 'online' : 'offline');
        this.updateNetworkBadge();
        
        if (isOnline) {
            console.log('📡 OfflineManager: Device is ONLINE. Syncing queue...');
            // The service-worker offline shell has no CSRF token. In that case skip
            // straight to the reload; init() on the real page performs the sync.
            if (this.getCsrfToken()) {
                await this.syncPendingSales();
                await this.syncOpenCarts();
                await this.mirrorOnlineCarts();
                await this.refreshLocalCatalog();
            }
            
            // Reload the page to restore live Django layouts and script event listeners
            this.showNotification('Connection restored! Syncing and updating storefront...');
            setTimeout(() => location.reload(), 1500);
        } else {
            console.warn('📡 OfflineManager: Device went OFFLINE.');
            this.showNotification('You are offline. Store POS is operating in local backup mode.', true);
            
            // For store pages, render the local catalog in-place instead of reloading.
            // Reloading would serve the cached page but then the health ping could flip
            // the status back to online causing a loop.
            if (window.location.pathname.includes('/store/')) {
                this.renderOfflineStore(1, '');
            }
            
            // Mid-sale drop on the live cart/checkout page: reload so the service
            // worker serves the offline shell, which continues the SAME (mirrored) cart.
            const path = window.location.pathname;
            const onLiveCartPage = (path.includes('/cart/') || path.includes('/checkout/')) &&
                                   !document.getElementById('offlineContentContainer');
            if (onLiveCartPage) {
                setTimeout(() => location.reload(), 800);
            }
        }
    }

    updateNetworkBadge() {
        const navbarBadge = document.getElementById('network-status');
        if (navbarBadge) {
            if (this.isOnline) {
                navbarBadge.className = 'badge bg-success';
                navbarBadge.innerHTML = '<i class="fa-solid fa-cloud-arrow-up me-1"></i> Online';
            } else {
                navbarBadge.className = 'badge bg-warning text-dark';
                navbarBadge.innerHTML = '<i class="fa-solid fa-signal-vertical-slash me-1"></i> Offline Mode';
            }
        }
    }

    async refreshLocalCatalog() {
        if (!this.isOnline || !this.branchId) return;
        
        try {
            const response = await fetch(`/ims/api/get-offline-data/${this.branchId}/`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            
            // Repopulate catalog store
            const transaction = this.db.transaction(['catalog'], 'readwrite');
            const store = transaction.objectStore(transaction.objectStoreNames[0]);
            
            // Clear existing
            await new Promise((res) => {
                const req = store.clear();
                req.onsuccess = () => res();
            });
            
            // Insert fresh catalog rows
            for (const item of data.products) {
                store.put(item);
            }
            
            // Save organization metadata
            if (data.organization_name) {
                await this.saveToStore('metadata', { key: 'org_name', value: data.organization_name });
            }
            if (data.organization_logo) {
                await this.saveToStore('metadata', { key: 'org_logo', value: data.organization_logo });
                // Prefetch to populate SW cache
                fetch(data.organization_logo).catch(err => console.warn('Failed to pre-cache logo:', err));
            }
            
            console.log(`📡 OfflineManager: Refreshed offline catalog and metadata with ${data.products.length} products.`);
        } catch (error) {
            console.error('❌ OfflineManager: Error refreshing catalog:', error);
        }
    }

    setupAddToCartInterception() {
        // Handle add to cart click interception when offline.
        // Use CAPTURE phase so this fires BEFORE cart.js's bubble-phase listener
        // can send a failing AJAX request to the server.
        document.body.addEventListener('click', (e) => {
            const addBtn = e.target.closest('.add-cart');
            if (!addBtn) return;
            
            // If offline, bypass standard Fetch AJAX request and run offline additions
            if (!this.isOnline) {
                e.preventDefault();
                e.stopImmediatePropagation();
                
                const inventoryId = addBtn.dataset.inventory;
                this.addCartItemOffline(inventoryId);
            }
        }, true);  // true = capture phase
    }

    async addCartItemOffline(inventoryId) {
        try {
            // 1. Fetch item from local catalog to check stock availability
            const item = await this.getFromStore('catalog', inventoryId);
            if (!item) {
                this.showNotification('Product details not found in cache.', true);
                return;
            }
            
            // 2. Fetch current active offline sale session (may be the mirrored online cart)
            let cart = await this.getActiveOfflineSale();
            const existingItem = cart.items.find(i => i.inventory_id === inventoryId);
            
            // Units this cart already reserves on the server are excluded from the
            // cached store_quantity, so add them back to get what this cart may hold.
            const available = this.availableQuantity(item, existingItem);
            const currentQty = existingItem ? existingItem.quantity : 0;
            
            if (available <= 0) {
                this.showNotification(`"${item.product_name}" is out of stock locally.`, true);
                return;
            }
            
            // 3. Update or append item
            if (currentQty + 1 > available) {
                this.showNotification(`Cannot add more. Max stock available: ${available}`, true);
                return;
            }
            if (existingItem) {
                existingItem.quantity += 1;
            } else {
                cart.items.push({ inventory_id: inventoryId, quantity: 1, reserved_qty: 0 });
            }
            cart.dirty = true;
            
            // 4. Save back to IndexedDB
            await this.saveToStore('offline_sales', cart);
            
            // 5. Update UI badge count
            this.updateCartBadgeCount(cart);
            this.showNotification(`"${item.product_name}" added to local cart.`);
            
        } catch (error) {
            console.error('❌ OfflineManager: Add offline item failed:', error);
            this.showNotification('Offline cart update failed.', true);
        }
    }

    /**
     * Max quantity a cart line may hold offline.
     * catalog.store_quantity already subtracts every open server cart (including this
     * one), so the units this cart reserved at mirror time are added back.
     */
    availableQuantity(catalogItem, cartItem) {
        const reserved = (cartItem && cartItem.reserved_qty) ? cartItem.reserved_qty : 0;
        return Math.max(0, (catalogItem ? catalogItem.store_quantity : 0) + reserved);
    }

    updateCartBadgeCount(cart) {
        const cartBadge = document.getElementById('addCart');
        if (cartBadge && cart) {
            const totalQty = cart.items.reduce((sum, item) => sum + item.quantity, 0);
            cartBadge.innerHTML = `${totalQty}`;
        }
    }

    async syncPendingSales() {
        if (this.syncInProgress || !this.isOnline || !this.branchId) return;
        this.syncInProgress = true;
        
        try {
            // Get all pending sales
            const sales = await this.getAllFromStore('pending_sales');
            if (sales.length === 0) {
                this.syncInProgress = false;
                return;
            }
            
            console.log(`📤 OfflineManager: Found ${sales.length} offline transactions to sync.`);
            this.showNotification(`Syncing ${sales.length} offline sale(s)...`);
            
            // Fetch CSRF token from DOM meta tags
            const token = this.getCsrfToken();
            if (!token) {
                // Offline shell page: defer until the real page loads (it has a token)
                return;
            }
            
            for (const sale of sales) {
                try {
                    const response = await fetch(`/ims/api/sync-sale/${this.branchId}/`, {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': token
                        },
                        body: JSON.stringify(sale)
                    });
                    
                    if (response.ok || response.status === 200 || response.status === 201) {
                        const resData = await response.json();
                        // Successfully synced, remove from queue
                        await this.deleteFromStore('pending_sales', sale.tempId);
                        this.queueNotice(`Sale of total ₦${sale.total_cart.toFixed(2)} synced successfully!`);
                        console.log(`✅ OfflineManager: Synced sale ${sale.tempId} -> Server ID: ${resData.sale_id}`);
                    } else if (response.status === 409) {
                        // Stock conflict, or the cart was already closed on another device.
                        // The server logged an Error Ticket for the owner to review.
                        const errData = await response.json();
                        await this.deleteFromStore('pending_sales', sale.tempId); // Clear to prevent stuck queues
                        this.queueNotice(`Sync warning: ${errData.error}`, true);
                        console.warn(`⚠️ OfflineManager: Sale ${sale.tempId} rejected due to conflict: ${errData.error}`);
                    } else {
                        throw new Error(`Server returned ${response.status}`);
                    }
                } catch (err) {
                    console.error(`❌ OfflineManager: Sync failed for sale ${sale.tempId}:`, err);
                    this.showNotification(`Failed to sync offline sale: ${err.message}`, true);
                    break; // Stop processing queue on transient network failures
                }
            }
        } catch (error) {
            console.error('❌ OfflineManager: Sync queue loop error:', error);
        } finally {
            this.syncInProgress = false;
        }
    }

    // Helper functions for IndexedDB Promise operations
    getFromStore(storeName, key) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readonly');
            const store = transaction.objectStore(storeName);
            const request = store.get(key);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    saveToStore(storeName, data) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readwrite');
            const store = transaction.objectStore(storeName);
            const request = store.put(data);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    deleteFromStore(storeName, key) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readwrite');
            const store = transaction.objectStore(storeName);
            const request = store.delete(key);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    getAllFromStore(storeName) {
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readonly');
            const store = transaction.objectStore(storeName);
            const request = store.getAll();
            request.onsuccess = () => resolve(request.result || []);
            request.onerror = () => reject(request.error);
        });
    }

    showNotification(message, isError = false) {
        // Call the global helper if it exists, otherwise define a fallback
        if (window.showNotification) {
            window.showNotification(message, isError);
            return;
        }
        
        const alertDiv = document.createElement('div');
        alertDiv.className = isError ? 'alert alert-danger' : 'alert alert-success';
        alertDiv.textContent = message;
        alertDiv.style.position = 'fixed';
        alertDiv.style.top = '80px';
        alertDiv.style.right = '20px';
        alertDiv.style.zIndex = '10000';
        alertDiv.style.maxWidth = '300px';
        alertDiv.style.boxShadow = '0 2px 8px rgba(0,0,0,0.15)';
        alertDiv.style.borderRadius = '4px';
        alertDiv.style.padding = '12px 15px';
        alertDiv.style.fontSize = '14px';
        alertDiv.style.fontWeight = '500';
        document.body.appendChild(alertDiv);
        
        setTimeout(() => {
            alertDiv.remove();
        }, 4000);
    }
    setupOfflineStoreInterception() {
        const searchForm = document.querySelector('.docs-search-form');
        if (searchForm) {
            searchForm.addEventListener('submit', (e) => {
                if (!this.isOnline) {
                    e.preventDefault();
                    const queryInput = searchForm.querySelector('input[name="product"]');
                    const query = queryInput ? queryInput.value.trim() : '';
                    this.renderOfflineStore(1, query);
                }
            });
        }

        if (!this.isOnline) {
            console.log('📡 OfflineManager: Active offline view detected. Rendering locally.');
            this.renderOfflineStore(1, '');
        }
    }

    async renderOfflineStore(page, query) {
        try {
            const allItems = await this.getAllFromStore('catalog');
            let filtered = allItems;
            
            if (query) {
                const lowerQuery = query.toLowerCase();
                filtered = allItems.filter(item => 
                    item.product_name.toLowerCase().includes(lowerQuery) ||
                    item.category_name.toLowerCase().includes(lowerQuery)
                );
            }
            
            const itemsPerPage = 12;
            const totalItems = filtered.length;
            const totalPages = Math.ceil(totalItems / itemsPerPage);
            const currentPage = Math.max(1, Math.min(page, totalPages));
            
            const startIndex = (currentPage - 1) * itemsPerPage;
            const pageItems = filtered.slice(startIndex, startIndex + itemsPerPage);
            
            // 1. Render grid
            const gridContainer = document.querySelector('.row.g-4');
            if (!gridContainer) {
                console.error('Grid container not found');
                return;
            }
            
            if (pageItems.length === 0) {
                gridContainer.innerHTML = `
                    <div class="col-12 text-center py-5">
                        <i class="fa-solid fa-magnifying-glass fa-3x text-muted mb-3"></i>
                        <h4>No products found</h4>
                        <p class="text-muted">Try adjusting your search criteria or clear the query.</p>
                    </div>
                `;
            } else {
                let html = '';
                for (const item of pageItems) {
                    const isOutOfStock = item.store_quantity <= 0;
                    html += `
                        <div class="col-6 col-md-4 col-xl-3 col-xxl-2">
                            <div class="app-card app-card-doc shadow-sm h-100 ${isOutOfStock ? 'opacity-50' : ''}"
                                 data-inventory-id="${item.id}"
                                 data-product-name="${item.product_name}"
                                 data-cost-price="${item.cost_price}"
                                 data-sale-price="${item.sale_price}"
                                 data-store-quantity="${item.store_quantity}">
                                <div class="app-card-thumb-holder p-3">
                                    ${!isOutOfStock ? `
                                        <a class="btn add-cart"
                                            data-inventory="${item.id}"
                                            data-action="add"
                                            data-branch="${this.branchId}">
                                        <span class="icon-holder">
                                            <i class="fa-solid fa-cart-plus"></i>
                                        </span>
                                        </a>
                                    ` : `
                                        <div class="btn btn-secondary disabled" style="cursor: not-allowed; opacity: 0.6;">
                                            <span class="icon-holder">
                                                <i class="fa-solid fa-ban"></i>
                                            </span>
                                        </div>
                                    `}
                                </div>
                                <div class="app-card-body p-3 has-card-actions">
                                    <h4 class="app-doc-title truncate mb-0"><a href="#">${item.product_name}</a></h4>
                                    <div class="app-doc-meta">
                                        <ul class="list-unstyled mb-0">
                                            <li><span class="text-muted">Category:</span> ${item.category_name}</li>
                                            <li><span class="text-muted">Price:</span> ₦${item.sale_price.toFixed(2)}</li>
                                            <li>
                                                ${!isOutOfStock ? `
                                                    <span class="badge bg-success">In Stock (${item.store_quantity})</span>
                                                ` : `
                                                    <span class="badge bg-danger">Out of Stock</span>
                                                `}
                                            </li>
                                        </ul>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                }
                gridContainer.innerHTML = html;
            }
            
            // 2. Render pagination
            let paginationContainer = document.querySelector('.pagination');
            if (!paginationContainer) {
                paginationContainer = document.createElement('div');
                paginationContainer.className = 'pagination';
                gridContainer.appendChild(paginationContainer);
            }
            if (paginationContainer) {
                if (totalPages <= 1) {
                    paginationContainer.innerHTML = '';
                    return;
                }
                
                let paginationHtml = `<span class="step-links"><nav aria-label="Page navigation"><ul class="pagination">`;
                if (currentPage > 1) {
                    paginationHtml += `<li class="page-item"><a class="page-link offline-page-link" href="#" data-page="${currentPage - 1}" style="color:grey;">previous</a></li>`;
                }
                for (let i = 1; i <= totalPages; i++) {
                    const isActive = i === currentPage;
                    paginationHtml += `
                        <span class="current">
                            <li class="page-item ${isActive ? 'active' : ''}">
                                <a class="page-link offline-page-link" href="#" data-page="${i}" style="${isActive ? 'background-color: #02296e; border-color: #02296e; color: white;' : 'color:grey;'}">${i}</a>
                            </li>
                        </span>
                    `;
                }
                if (currentPage < totalPages) {
                    paginationHtml += `<li class="page-item"><a class="page-link offline-page-link" href="#" data-page="${currentPage + 1}" style="color:grey;">next</a></li>`;
                }
                paginationHtml += `</ul></nav></span>`;
                paginationContainer.innerHTML = paginationHtml;
                
                paginationContainer.querySelectorAll('.offline-page-link').forEach(link => {
                    link.addEventListener('click', (e) => {
                        e.preventDefault();
                        const targetPage = parseInt(link.dataset.page);
                        this.renderOfflineStore(targetPage, query);
                        window.scrollTo({ top: 0, behavior: 'smooth' });
                    });
                });
            }
        } catch (error) {
            console.error('❌ OfflineManager: Render offline store grid failed:', error);
        }
    }
    // ------------------------------------------------------------------
    // Unified cart: mirroring, active-cart selection and reconciliation
    // ------------------------------------------------------------------

    getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || null;
    }

    activeSaleKey() {
        return `active_offline_sale_${this.branchId}`;
    }

    newLocalSale() {
        return {
            id: 'temp-sale-' + Math.random().toString(36).substring(2, 11),
            server_sale_id: null,       // created while offline; promoted on reconnect
            branch_id: this.branchId,
            date_added: new Date().toISOString(),
            items: [],
            dirty: false,
            cancelled: false
        };
    }

    /**
     * Notices that must survive the post-sync reload (sessionStorage-backed).
     */
    queueNotice(message, isError = false) {
        this.showNotification(message, isError);
        try {
            const notices = JSON.parse(sessionStorage.getItem('quicksales_pending_notices') || '[]');
            notices.push({ message, isError });
            sessionStorage.setItem('quicksales_pending_notices', JSON.stringify(notices.slice(-10)));
        } catch (e) { /* ignore */ }
    }

    flushQueuedNotices() {
        try {
            const notices = JSON.parse(sessionStorage.getItem('quicksales_pending_notices') || '[]');
            sessionStorage.removeItem('quicksales_pending_notices');
            notices.forEach((n, idx) => {
                setTimeout(() => this.showNotification(n.message, n.isError), 300 + idx * 600);
            });
        } catch (e) { /* ignore */ }
    }

    /** Debounced mirror, called by cart.js after each successful online cart action. */
    scheduleMirror() {
        clearTimeout(this._mirrorTimer);
        this._mirrorTimer = setTimeout(() => this.mirrorOnlineCarts(), 300);
    }

    /**
     * Pull the user's open server carts into IndexedDB, keyed by Sale UUID, so that
     * if the network drops the SAME cart continues offline. Dirty (edited offline)
     * or tombstoned records are never overwritten.
     */
    async mirrorOnlineCarts() {
        if (!this.isOnline || !this.branchId || !this.db) return;
        if (this._mirrorInFlight) return this._mirrorInFlight;

        this._mirrorInFlight = (async () => {
            try {
                const response = await fetch(`/ims/api/open-sales/${this.branchId}/`, {
                    credentials: 'same-origin',
                    cache: 'no-store',
                    headers: { 'Accept': 'application/json' }
                });
                const contentType = response.headers.get('content-type') || '';
                if (!response.ok || !contentType.includes('application/json')) {
                    throw new Error(`HTTP ${response.status}`);
                }
                const data = await response.json();
                const serverSales = data.sales || [];
                const serverIds = new Set(serverSales.map(s => s.id));

                // Sales already checked out offline (awaiting sync) must not reappear as open carts
                const pending = await this.getAllFromStore('pending_sales');
                const pendingServerIds = new Set(pending.map(p => p.server_sale_id).filter(Boolean));

                const localSales = await this.getAllOfflineSales(true);
                const localById = new Map(localSales.map(s => [s.id, s]));

                // Drop clean mirrored carts that are no longer open on the server
                for (const rec of localSales) {
                    if (rec.server_sale_id && !serverIds.has(rec.server_sale_id) && !rec.dirty && !rec.cancelled) {
                        await this.deleteFromStore('offline_sales', rec.id);
                    }
                }

                const now = new Date().toISOString();
                for (const s of serverSales) {
                    if (pendingServerIds.has(s.id)) continue;
                    const existing = localById.get(s.id);
                    if (existing && (existing.dirty || existing.cancelled)) continue;

                    await this.saveToStore('offline_sales', {
                        id: s.id,
                        server_sale_id: s.id,
                        branch_id: this.branchId,
                        date_added: s.date_added || now,
                        items: (s.items || []).map(i => ({
                            inventory_id: i.inventory_id,
                            quantity: i.quantity,
                            reserved_qty: i.quantity
                        })),
                        dirty: false,
                        cancelled: false,
                        last_mirrored_at: now
                    });
                }

                if (data.active_sale_id && !pendingServerIds.has(data.active_sale_id)) {
                    sessionStorage.setItem(this.activeSaleKey(), data.active_sale_id);
                } else {
                    const activeId = sessionStorage.getItem(this.activeSaleKey());
                    if (activeId && !(await this.getFromStore('offline_sales', activeId))) {
                        sessionStorage.removeItem(this.activeSaleKey());
                    }
                }
            } catch (error) {
                console.warn('📡 OfflineManager: Could not mirror online carts:', error);
            } finally {
                this._mirrorInFlight = null;
            }
        })();
        return this._mirrorInFlight;
    }

    /**
     * Push carts that were edited, created or cancelled offline (but not checked out)
     * back to the server. Quantities are capped server-side to available stock.
     */
    async syncOpenCarts() {
        if (!this.isOnline || !this.branchId || !this.db) return;
        const token = this.getCsrfToken();
        if (!token) return;

        const all = await this.getAllOfflineSales(true);
        const activeId = sessionStorage.getItem(this.activeSaleKey());

        for (const rec of all) {
            const isLocalOnly = !rec.server_sale_id;
            const hasItems = rec.items && rec.items.length > 0;

            // Empty or cancelled offline-only carts never reached the server: just drop them
            if (isLocalOnly && (!hasItems || rec.cancelled)) {
                await this.deleteFromStore('offline_sales', rec.id);
                if (rec.id === activeId) sessionStorage.removeItem(this.activeSaleKey());
                continue;
            }
            // Clean mirrored carts need no reconciliation
            if (!isLocalOnly && !rec.dirty && !rec.cancelled) continue;

            try {
                const response = await fetch(`/ims/api/sync-cart/${this.branchId}/`, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': token
                    },
                    body: JSON.stringify({
                        local_id: rec.id,
                        server_sale_id: rec.server_sale_id || null,
                        items: (rec.items || []).map(i => ({ inventory_id: i.inventory_id, quantity: i.quantity })),
                        cancelled: !!rec.cancelled,
                        make_active: rec.id === activeId
                    })
                });
                if (!response.ok) throw new Error(`Server returned ${response.status}`);
                const data = await response.json();

                await this.deleteFromStore('offline_sales', rec.id);

                if (data.server_sale_id && !data.cancelled && data.sale) {
                    // Re-key the cart under its server Sale UUID
                    await this.saveToStore('offline_sales', {
                        id: data.server_sale_id,
                        server_sale_id: data.server_sale_id,
                        branch_id: this.branchId,
                        date_added: data.sale.date_added || rec.date_added,
                        items: (data.sale.items || []).map(i => ({
                            inventory_id: i.inventory_id,
                            quantity: i.quantity,
                            reserved_qty: i.quantity
                        })),
                        dirty: false,
                        cancelled: false,
                        last_mirrored_at: new Date().toISOString()
                    });
                    if (rec.id === activeId) sessionStorage.setItem(this.activeSaleKey(), data.server_sale_id);
                } else if (rec.id === activeId) {
                    sessionStorage.removeItem(this.activeSaleKey());
                }

                for (const adj of (data.adjustments || [])) {
                    if (adj.reason === 'insufficient_stock') {
                        this.queueNotice(`"${adj.product_name}" reduced from ${adj.requested} to ${adj.applied}. Only ${adj.applied} left in stock.`, true);
                    } else {
                        this.queueNotice('An item in your cart is no longer available and was removed.', true);
                    }
                }
                if (data.conflict) {
                    this.queueNotice('A cart was closed on another device while you were offline. Your items were moved to a new open sale.', true);
                }
            } catch (error) {
                console.error(`❌ OfflineManager: Cart sync failed for ${rec.id}:`, error);
                break; // Transient failure: retry on next load
            }
        }
    }

    async getActiveOfflineSale() {
        const key = this.activeSaleKey();
        const activeId = sessionStorage.getItem(key);
        let sale = activeId ? await this.getFromStore('offline_sales', activeId) : null;

        if (!sale || sale.cancelled || sale.branch_id !== this.branchId) {
            const sales = await this.getAllOfflineSales();
            sale = sales.length > 0 ? sales[sales.length - 1] : null;
            if (!sale) {
                sale = this.newLocalSale();
                await this.saveToStore('offline_sales', sale);
            }
            sessionStorage.setItem(key, sale.id);
        }
        if (!Array.isArray(sale.items)) sale.items = [];
        return sale;
    }

    /** Open carts for this branch, oldest first. Tombstoned carts are hidden unless requested. */
    async getAllOfflineSales(includeCancelled = false) {
        const sales = await this.getAllFromStore('offline_sales');
        return sales
            .filter(s => s.branch_id === this.branchId && (includeCancelled || !s.cancelled))
            .sort((a, b) => String(a.date_added || '').localeCompare(String(b.date_added || '')));
    }

    async createOfflineSale() {
        const sale = this.newLocalSale();
        await this.saveToStore('offline_sales', sale);
        sessionStorage.setItem(this.activeSaleKey(), sale.id);
        return sale.id;
    }

    async cancelOfflineSale(saleId) {
        const sale = await this.getFromStore('offline_sales', saleId);
        if (sale && sale.server_sale_id) {
            // Server-backed cart: keep a tombstone so the cancel is applied on reconnect
            sale.cancelled = true;
            sale.dirty = true;
            await this.saveToStore('offline_sales', sale);
        } else {
            await this.deleteFromStore('offline_sales', saleId);
        }
        if (sessionStorage.getItem(this.activeSaleKey()) === saleId) {
            sessionStorage.removeItem(this.activeSaleKey());
            // Force create/select another open sale
            await this.getActiveOfflineSale();
        }
    }

    /** Remove a cart that has just been checked out (online or offline). */
    async removeOfflineSaleAfterCheckout(saleId) {
        if (!this.db || !saleId) return;
        await this.deleteFromStore('offline_sales', saleId);
        if (sessionStorage.getItem(this.activeSaleKey()) === saleId) {
            sessionStorage.removeItem(this.activeSaleKey());
        }
    }
}

// Instantiate globally
window.offlineManager = new OfflineManager();
