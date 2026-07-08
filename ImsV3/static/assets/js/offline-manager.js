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
            
            if (this.branchId) {
                // If online, refresh local product cache and trigger background sync
                if (this.isOnline) {
                    await this.syncPendingSales();
                    await this.refreshLocalCatalog();
                    this.triggerActivePrecaching().catch(err => {
                        console.error('📡 OfflineManager: Active pre-caching failed:', err);
                    });
                } else {
                    const cart = await this.getActiveOfflineSale();
                    this.updateCartBadgeCount(cart);
                }
                
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
            await this.syncPendingSales();
            await this.refreshLocalCatalog();
            
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
            
            if (item.store_quantity <= 0) {
                this.showNotification(`"${item.product_name}" is out of stock locally.`, true);
                return;
            }
            
            // 2. Fetch current active offline sale session
            let cart = await this.getActiveOfflineSale();
            
            // 3. Update or append item
            const existingItem = cart.items.find(i => i.inventory_id === inventoryId);
            if (existingItem) {
                if (existingItem.quantity + 1 > item.store_quantity) {
                    this.showNotification(`Cannot add more. Max stock available: ${item.store_quantity}`, true);
                    return;
                }
                existingItem.quantity += 1;
            } else {
                cart.items.push({ inventory_id: inventoryId, quantity: 1 });
            }
            
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
            const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || window.csrftoken;
            
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
                        this.showNotification(`Sale of total ₦${sale.total_cart.toFixed(2)} synced successfully!`);
                        console.log(`✅ OfflineManager: Synced sale ${sale.tempId} -> Server ID: ${resData.sale_id}`);
                    } else if (response.status === 409) {
                        // Stock conflict occurred and has been logged on the server.
                        const errData = await response.json();
                        await this.deleteFromStore('pending_sales', sale.tempId); // Clear to prevent stuck queues
                        this.showNotification(`Sync warning: Stock conflict. ${errData.error}`, true);
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
    async getActiveOfflineSale() {
        let activeId = sessionStorage.getItem(`active_offline_sale_${this.branchId}`);
        if (!activeId) {
            const sales = await this.getAllOfflineSales();
            if (sales.length > 0) {
                activeId = sales[0].id;
                sessionStorage.setItem(`active_offline_sale_${this.branchId}`, activeId);
            } else {
                activeId = 'temp-sale-' + Math.random().toString(36).substring(2, 11);
                const defaultSale = {
                    id: activeId,
                    branch_id: this.branchId,
                    date_added: new Date().toISOString(),
                    items: []
                };
                await this.saveToStore('offline_sales', defaultSale);
                sessionStorage.setItem(`active_offline_sale_${this.branchId}`, activeId);
            }
        }
        
        let sale = await this.getFromStore('offline_sales', activeId);
        if (!sale) {
            activeId = 'temp-sale-' + Math.random().toString(36).substring(2, 11);
            sale = {
                id: activeId,
                branch_id: this.branchId,
                date_added: new Date().toISOString(),
                items: []
            };
            await this.saveToStore('offline_sales', sale);
            sessionStorage.setItem(`active_offline_sale_${this.branchId}`, activeId);
        }
        return sale;
    }

    async getAllOfflineSales() {
        const sales = await this.getAllFromStore('offline_sales');
        return sales.filter(s => s.branch_id === this.branchId);
    }

    async createOfflineSale() {
        const newId = 'temp-sale-' + Math.random().toString(36).substring(2, 11);
        const sale = {
            id: newId,
            branch_id: this.branchId,
            date_added: new Date().toISOString(),
            items: []
        };
        await this.saveToStore('offline_sales', sale);
        sessionStorage.setItem(`active_offline_sale_${this.branchId}`, newId);
        return newId;
    }

    async cancelOfflineSale(saleId) {
        await this.deleteFromStore('offline_sales', saleId);
        const activeId = sessionStorage.getItem(`active_offline_sale_${this.branchId}`);
        if (activeId === saleId) {
            sessionStorage.removeItem(`active_offline_sale_${this.branchId}`);
            // Force create/select another open sale
            await this.getActiveOfflineSale();
        }
    }
}

// Instantiate globally
window.offlineManager = new OfflineManager();
