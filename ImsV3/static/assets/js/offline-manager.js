/**
 * Offline Manager - Handles all offline-first functionality
 * Manages IndexedDB for caching and syncing data
 */

class OfflineManager {
    constructor() {
        this.dbName = 'quicksales_offline';
        this.version = 1;
        this.db = null;
        this.isOnline = navigator.onLine;
        this.syncInProgress = false;
        this.pendingSalesCount = 0;
        
        // Idle detection for auto-logout
        this.IDLE_TIMEOUT = 600000; // 10 minutes in milliseconds
        this.idleTimer = null;
        this.lastActivityTime = Date.now();
        
        this.init();
    }

    /**
     * Initialize offline manager and set up event listeners
     */
    async init() {
        try {
            // Open IndexedDB
            await this.openDatabase();
            // Initialize pending sales count from DB
            await this.refreshPendingCount();
            
            // Set initial online status
            this.isOnline = navigator.onLine;
            console.log('📶 Initial online status:', this.isOnline);
            
            // Load initial offline data on page load if online
            if (this.isOnline) {
                console.log('📥 Loading offline data cache...');
                await this.loadOfflineData().catch(e => console.warn('Could not preload offline data:', e));
            }
            
            // Set up online/offline listeners
            window.addEventListener('online', () => this.onOnline());
            window.addEventListener('offline', () => this.onOffline());
            
            // Also poll navigator.onLine status every 2 seconds for DevTools offline mode
            setInterval(() => {
                const currentOnlineStatus = navigator.onLine;
                if (currentOnlineStatus !== this.isOnline) {
                    console.log('🔄 Online status changed via polling:', currentOnlineStatus);
                    this.isOnline = currentOnlineStatus;
                    if (currentOnlineStatus) {
                        this.onOnline();
                    } else {
                        this.onOffline();
                    }
                }
            }, 1000); // Check every 1 second for faster detection

            // Background sync poll every 10 seconds when online
            setInterval(() => this.attemptBackgroundSync(), 10000);
            
            // Check for pending syncs every 30 seconds
            setInterval(() => this.checkAndSync(), 30000);
            
            // Refresh offline data every 5 minutes when online
            setInterval(() => {
                if (this.isOnline) {
                    this.loadOfflineData().catch(e => console.warn('Periodic offline data refresh failed:', e));
                }
            }, 300000); // 5 minutes
            
            // Set up idle detection for auto-logout
            this.setupIdleDetection();
            
            console.log('✅ Offline Manager initialized. Online:', navigator.onLine);
            this.updateUI();
        } catch (error) {
            console.error('❌ Failed to initialize Offline Manager:', error);
        }
    }
    
    /**
     * Load offline data from server and cache it
     */
    async loadOfflineData() {
        try {
            console.log('🔄 Fetching offline data from server...');
            const response = await fetch('/ims/api/get-offline-data/');
            
            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                console.log(`📥 Caching ${data.products.length} products and ${data.inventory.length} inventory items`);
                await this.cacheProductData(data.products, data.inventory);
                console.log('✅ Offline data cache updated');
            } else {
                console.warn('⚠️ Server returned success: false');
            }
        } catch (error) {
            console.warn('⚠️ Failed to load offline data:', error);
            // Don't throw - this is not critical
        }
    }

    async refreshPendingCount() {
        try {
            const pending = await this.getPendingSales();
            this.pendingSalesCount = pending.length;
        } catch (e) {
            console.warn('Could not refresh pending count:', e);
        }
    }

    async attemptBackgroundSync() {
        if (!navigator.onLine || this.syncInProgress) return;
        try {
            const [offlineCart, pendingSales] = await Promise.all([
                this.getOfflineCart(),
                this.getPendingSales()
            ]);
            if (offlineCart.length > 0) {
                await this.syncOfflineCart(offlineCart);
            }
            if (pendingSales.length > 0) {
                await this.checkAndSync();
            }
        } catch (e) {
            console.warn('Background sync attempt failed:', e);
        }
    }

    /**
     * Open or create IndexedDB database
     */
    openDatabase() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.version);

            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                this.db = request.result;
                console.log('✅ IndexedDB opened');
                resolve(this.db);
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                
                // Create object stores if they don't exist
                if (!db.objectStoreNames.contains('products')) {
                    db.createObjectStore('products', { keyPath: 'id' });
                }
                if (!db.objectStoreNames.contains('inventory')) {
                    db.createObjectStore('inventory', { keyPath: 'id' });
                }
                if (!db.objectStoreNames.contains('pendingSales')) {
                    db.createObjectStore('pendingSales', { keyPath: 'tempId', autoIncrement: true });
                }
                if (!db.objectStoreNames.contains('syncQueue')) {
                    db.createObjectStore('syncQueue', { keyPath: 'id', autoIncrement: true });
                }
                if (!db.objectStoreNames.contains('cart')) {
                    db.createObjectStore('cart', { keyPath: 'id', autoIncrement: true });
                }
            };
        });
    }

    /**
     * Cache products and inventory data from server
     */
    async cacheProductData(products, inventory) {
        try {
            const tx = this.db.transaction(['products', 'inventory'], 'readwrite');
            
            // Clear old data
            tx.objectStore('products').clear();
            tx.objectStore('inventory').clear();
            
            // Add new data
            products.forEach(product => {
                tx.objectStore('products').add(product);
            });
            
            inventory.forEach(item => {
                tx.objectStore('inventory').add(item);
            });

            return new Promise((resolve, reject) => {
                tx.oncomplete = () => {
                    console.log('✅ Cached', products.length, 'products and', inventory.length, 'inventory items');
                    resolve();
                };
                tx.onerror = () => reject(tx.error);
            });
        } catch (error) {
            console.error('❌ Error caching data:', error);
        }
    }

    /**
     * Save a pending sale for later sync
     */
    async savePendingSale(saleData) {
        try {
            const tx = this.db.transaction('pendingSales', 'readwrite');
            const store = tx.objectStore('pendingSales');
            
            const saleWithMetadata = {
                ...saleData,
                tempId: Date.now() + Math.random(),
                syncStatus: 'pending',
                createdAt: new Date().toISOString(),
                retryCount: 0
            };

            store.add(saleWithMetadata);

            return new Promise((resolve, reject) => {
                tx.oncomplete = () => {
                    console.log('✅ Pending sale saved locally');
                    this.pendingSalesCount++;
                    this.updateUI();
                    resolve(saleWithMetadata.tempId);
                };
                tx.onerror = () => reject(tx.error);
            });
        } catch (error) {
            console.error('❌ Error saving pending sale:', error);
        }
    }

    /**
     * Get all pending sales
     */
    async getPendingSales() {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction('pendingSales', 'readonly');
            const store = tx.objectStore('pendingSales');
            const request = store.getAll();

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Remove a pending sale after successful sync
     */
    async removePendingSale(tempId) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction('pendingSales', 'readwrite');
            const store = tx.objectStore('pendingSales');
            const request = store.delete(tempId);

            request.onsuccess = () => {
                this.pendingSalesCount--;
                this.updateUI();
                resolve();
            };
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Get cached inventory for a product
     */
    async getCachedInventory(productId) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction('inventory', 'readonly');
            const store = tx.objectStore('inventory');
            const request = store.get(productId);

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Update cached inventory when making a local sale
     */
    async decrementCachedInventory(productId, quantity) {
        try {
            const tx = this.db.transaction('inventory', 'readwrite');
            const store = tx.objectStore('inventory');
            const request = store.get(productId);

            request.onsuccess = () => {
                const inventory = request.result;
                if (inventory) {
                    inventory.quantity = Math.max(0, (inventory.quantity || 0) - quantity);
                    inventory.lastModified = new Date().toISOString();
                    store.put(inventory);
                }
            };

            return new Promise((resolve, reject) => {
                tx.oncomplete = () => resolve();
                tx.onerror = () => reject(tx.error);
            });
        } catch (error) {
            console.error('❌ Error decrementing cached inventory:', error);
        }
    }

    /**
     * Handle when connection comes back online
     */
    async onOnline() {
        this.isOnline = true;
        console.log('🟢 Back online!');
        this.updateUI();
        
        // Refresh offline data cache in background
        this.loadOfflineData().catch(e => console.warn('Background offline data refresh failed:', e));
        
        // Check for offline cart items to sync
        const offlineCart = await this.getOfflineCart();
        const pendingSales = await this.getPendingSales();
        
        // Show what's being synced
        let syncCount = 0;
        if (offlineCart.length > 0) syncCount++;
        if (pendingSales.length > 0) syncCount++;
        
        if (syncCount > 0) {
            let syncMsg = '🔄 Syncing: ';
            if (offlineCart.length > 0) {
                syncMsg += `${offlineCart.length} cart item(s)`;
                if (pendingSales.length > 0) syncMsg += ' + ';
            }
            if (pendingSales.length > 0) {
                syncMsg += `${pendingSales.length} pending sale(s)`;
            }
            this.showSyncNotification(syncMsg, 'info');
        }
        
        // Sync cart first if there are items
        if (offlineCart.length > 0) {
            await this.syncOfflineCart(offlineCart);
        }
        
        // Then sync pending sales
        if (pendingSales.length > 0) {
            await this.checkAndSync();
        }
    }

    /**
     * Sync offline cart items to server
     */
    async syncOfflineCart(cartItems) {
        try {
            console.log(`📦 Syncing ${cartItems.length} cart items...`);
            
            let successCount = 0;
            let failCount = 0;
            let lastCartCount = 0;
            
            for (const item of cartItems) {
                try {
                    const branchId = item.branchId;
                    if (!branchId) {
                        console.error('❌ No branch ID for item:', item.inventoryId);
                        failCount++;
                        continue;
                    }
                    
                    const url = `/ims/update_cart/${branchId}/`;
                    console.log('📤 Syncing to:', url, 'Item:', item.inventoryId);
                    
                    const response = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCsrfToken()
                        },
                        body: JSON.stringify({
                            inventoryId: item.inventoryId,
                            action: 'add'
                        })
                    });

                    if (response.ok) {
                        const data = await response.json();
                        console.log('✅ Cart item synced:', item.inventoryId, data);
                        // Store the cart count from the response
                        if (data.qty !== undefined) {
                            lastCartCount = data.qty;
                        }
                        successCount++;
                    } else {
                        const errorText = await response.text();
                        console.error('❌ Failed to sync cart item:', item.inventoryId, response.status, errorText);
                        failCount++;
                    }
                } catch (error) {
                    console.error('❌ Error syncing cart item:', error);
                    failCount++;
                }
            }
            
            // Clear offline cart after syncing
            if (successCount > 0) {
                await this.clearOfflineCart();
                this.showSyncNotification(
                    `✅ Cart synced! ${successCount} item(s) added.${failCount > 0 ? ` ${failCount} failed.` : ''}`,
                    successCount > failCount ? 'success' : 'warning'
                );
                
                // Update cart count display with actual server count
                const cartElement = document.getElementById('addCart');
                if (cartElement && lastCartCount > 0) {
                    cartElement.innerHTML = `${lastCartCount}`;
                    console.log('✅ Updated cart count to:', lastCartCount);
                }
            } else {
                this.showSyncNotification('⚠️ Cart sync failed - will retry later', 'warning');
            }
        } catch (error) {
            console.error('❌ Cart sync error:', error);
            this.showSyncNotification('⚠️ Cart sync incomplete - will retry', 'warning');
        }
    }

    /**
     * Handle when connection goes offline
     */
    onOffline() {
        this.isOnline = false;
        console.log('🔴 Connection lost - Offline mode enabled');
        this.updateUI();
        this.showSyncNotification('📡 Connection lost - switched to offline mode', 'warning');
    }

    /**
     * Check for pending sales and sync with server
     */
    async checkAndSync() {
        if (!this.isOnline || this.syncInProgress) {
            return;
        }

        this.syncInProgress = true;
        // Skip permanently failed sales (we don't retry or toast them)
        const pendingSales = (await this.getPendingSales()).filter(
            (sale) => sale.syncStatus !== 'failed'
        );
        this.pendingSalesCount = pendingSales.length;

        if (pendingSales.length === 0) {
            this.syncInProgress = false;
            return;
        }

        console.log(`Syncing ${pendingSales.length} pending sales...`);
        this.updateUI(true);
        let successCount = 0;
        let failCount = 0;

        for (const sale of pendingSales) {
            try {
                // Build payload expected by backend
                const items = (sale.cartItems || sale.items || []).map((item) => {
                    const inventory = item.inventory || {};
                    const productId = item.product_id || inventory.product_id || item.inventoryId;
                    console.log('📦 Sync item:', {
                        productId,
                        quantity: item.quantity,
                        itemProduct: item.product_id,
                        inventoryProduct: inventory.product_id,
                        fallbackInventoryId: item.inventoryId
                    });
                    return {
                        product_id: productId,
                        quantity: parseInt(item.quantity || 1),
                        unit_price: item.unitPrice ?? inventory.sale_price ?? inventory.cost_price ?? 0,
                        cost_price: item.cost_price ?? inventory.cost_price ?? 0,
                    };
                });

                const payload = {
                    items,
                    total_amount: sale.total ?? sale.total_amount ?? 0,
                    payment_method: sale.paymentMethod || sale.payment_method || 'cash',
                    payment_status: sale.payment_status || 'pending',
                    tempId: sale.tempId,
                };
                
                console.log('🔄 Syncing payload:', payload);

                const response = await fetch('/ims/api/sync-sale/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    const result = await response.json();
                    await this.removePendingSale(sale.tempId);
                    console.log('✅ Sale synced:', result);
                    successCount++;
                } else {
                    let errorData = {};
                    try {
                        errorData = await response.json();
                    } catch {
                        errorData = { message: await response.text() };
                    }
                    console.warn('❌ Sale sync failed:', response.status, errorData);
                    console.warn('Payload that failed:', JSON.stringify(payload, null, 2));
                    sale.retryCount++;
                    if (sale.retryCount < 3) {
                        await this.updatePendingSaleRetryCount(sale.tempId, sale.retryCount);
                    } else {
                        failCount++;
                        // Mark as permanently failed and silence toasts
                        await this.markPendingSaleFailed(sale.tempId, errorData);
                        console.warn('❌ Sale marked failed after 3 attempts:', {
                            tempId: sale.tempId,
                            error: errorData
                        });
                    }
                }
            } catch (error) {
                console.error('❌ Sync error:', error);
                sale.retryCount++;
                failCount++;
                this.showSyncNotification('Network error during sync. Retrying...', 'warning');
            }
        }

        this.syncInProgress = false;
        this.updateUI();

        // Show completion message
        if (successCount > 0 || failCount > 0) {
            this.showSyncNotification(
                `✅ Sync complete! ${successCount} sale(s) stored.${failCount > 0 ? ` ${failCount} failed.` : ''}`,
                failCount > 0 ? 'warning' : 'success'
            );
        }
    }

    /**
     * Update retry count for pending sale
     */
    async updatePendingSaleRetryCount(tempId, retryCount) {
        const tx = this.db.transaction('pendingSales', 'readwrite');
        const store = tx.objectStore('pendingSales');
        const request = store.get(tempId);

        request.onsuccess = () => {
            const sale = request.result;
            sale.retryCount = retryCount;
            store.put(sale);
        };
    }

    /**
     * Mark a pending sale as permanently failed to stop further retries/toasts
     */
    async markPendingSaleFailed(tempId, errorData = {}) {
        const tx = this.db.transaction('pendingSales', 'readwrite');
        const store = tx.objectStore('pendingSales');
        const request = store.get(tempId);

        request.onsuccess = () => {
            const sale = request.result;
            if (!sale) return;
            sale.syncStatus = 'failed';
            sale.lastError = errorData;
            store.put(sale);
        };
    }

    /**
     * Update UI with offline status and pending sales count
     */
    updateUI(syncing = false) {
        const indicator = document.getElementById('offlineIndicator');
        if (!indicator) {
            console.warn('⚠️ Offline indicator element not found in DOM');
            return;
        }

        console.log('📊 Updating UI - Online:', this.isOnline, 'Syncing:', syncing, 'Pending:', this.pendingSalesCount);

        if (this.isOnline) {
            indicator.className = 'offline-indicator online';
            indicator.innerHTML = `<span class="status-dot online"></span> Online`;
            
            if (this.pendingSalesCount > 0 && !syncing) {
                indicator.innerHTML += ` | <span class="pending-badge">${this.pendingSalesCount} pending</span>`;
            }
            if (syncing) {
                indicator.innerHTML = `<span class="status-dot syncing"></span> Syncing...`;
            }
        } else {
            indicator.className = 'offline-indicator offline';
            indicator.innerHTML = `<span class="status-dot offline"></span> Offline Mode | ${this.pendingSalesCount} sales queued`;
        }
        
        console.log('✅ UI Updated - Current class:', indicator.className);
    }

    /**
     * Show notification to user
     */
    showNotification(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type}`;
        alertDiv.textContent = message;
        alertDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 9999;';
        document.body.appendChild(alertDiv);
        
        setTimeout(() => alertDiv.remove(), 5000);
    }

    /**
     * Show sync notification with better styling
     */
    showSyncNotification(message, type = 'info') {
        // Create toast notification container if it doesn't exist
        let container = document.getElementById('sync-toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'sync-toast-container';
            container.style.cssText = `
                position: fixed;
                top: 100px;
                right: 20px;
                z-index: 10001;
                display: flex;
                flex-direction: column;
                gap: 10px;
                max-width: 400px;
            `;
            document.body.appendChild(container);
        }

        // Create toast element
        const toast = document.createElement('div');
        const bgColor = type === 'success' ? '#4CAF50' : type === 'error' ? '#f44336' : '#ff9800';
        const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : '⚠️';

        toast.innerHTML = `
            <div style="
                background: ${bgColor};
                color: white;
                padding: 16px;
                border-radius: 4px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                animation: slideInRight 0.3s ease;
                display: flex;
                align-items: center;
                gap: 12px;
                font-size: 14px;
                font-weight: 500;
            ">
                <span style="font-size: 20px;">${icon}</span>
                <span>${message}</span>
            </div>
        `;

        container.appendChild(toast);

        // Auto-remove after 4 seconds
        setTimeout(() => {
            toast.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    /**
     * Get CSRF token from cookie or meta tag
     */
    getCsrfToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        if (token) return token.value;
        
        return document.cookie
            .split(';')
            .find(c => c.trim().startsWith('csrftoken='))
            ?.split('=')[1] || '';
    }

    /**
     * Add item to offline cart
     */
    async addToOfflineCart(inventoryId, action = 'add', quantity = 1, branchId = null) {
        return new Promise((resolve, reject) => {
            // Get branch ID from page if not provided
            if (!branchId) {
                const branchElement = document.querySelector('[data-branch]');
                branchId = branchElement ? branchElement.dataset.branch : null;
            }
            
            const tx = this.db.transaction('cart', 'readwrite');
            const store = tx.objectStore('cart');
            
            // Get existing cart item if it exists
            const getRequest = store.index ? store.getAllKeys() : store.getAll();
            
            const getAllRequest = store.getAll();
            getAllRequest.onsuccess = () => {
                const allItems = getAllRequest.result;
                const existingItem = allItems.find(item => item.inventoryId == inventoryId);
                
                if (existingItem && action === 'add') {
                    // Update quantity
                    existingItem.quantity = (existingItem.quantity || 1) + quantity;
                    existingItem.lastModified = new Date().toISOString();
                    if (branchId) existingItem.branchId = branchId;
                    store.put(existingItem);
                } else if (existingItem && action === 'remove') {
                    // Remove item
                    store.delete(existingItem.id);
                } else if (!existingItem && action === 'add') {
                    // Add new item
                    store.add({
                        inventoryId: inventoryId,
                        quantity: quantity,
                        branchId: branchId,
                        addedAt: new Date().toISOString(),
                        lastModified: new Date().toISOString()
                    });
                }
            };

            tx.oncomplete = () => {
                console.log(`✅ Offline cart updated: ${action} inventory ${inventoryId}`);
                resolve();
            };
            tx.onerror = () => reject(tx.error);
        });
    }

    /**
     * Update cart item quantity
     */
    async updateCartQuantity(inventoryId, quantity) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction('cart', 'readwrite');
            const store = tx.objectStore('cart');
            const getAllRequest = store.getAll();

            getAllRequest.onsuccess = () => {
                const allItems = getAllRequest.result;
                const existingItem = allItems.find(item => item.inventoryId == inventoryId);
                
                if (existingItem) {
                    existingItem.quantity = parseInt(quantity);
                    existingItem.lastModified = new Date().toISOString();
                    store.put(existingItem);
                }
            };

            tx.oncomplete = () => {
                console.log(`✅ Offline cart quantity updated: ${inventoryId} = ${quantity}`);
                resolve();
            };
            tx.onerror = () => reject(tx.error);
        });
    }

    /**
     * Get cart count
     */
    async getCartCount() {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction('cart', 'readonly');
            const store = tx.objectStore('cart');
            const getAllRequest = store.getAll();

            getAllRequest.onsuccess = () => {
                const allItems = getAllRequest.result;
                const totalQuantity = allItems.reduce((sum, item) => sum + (item.quantity || 0), 0);
                resolve(totalQuantity);
            };
            getAllRequest.onerror = () => reject(getAllRequest.error);
        });
    }

    /**
     * Get all offline cart items
     */
    async getOfflineCart() {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction('cart', 'readonly');
            const store = tx.objectStore('cart');
            const getAllRequest = store.getAll();

            getAllRequest.onsuccess = () => resolve(getAllRequest.result);
            getAllRequest.onerror = () => reject(getAllRequest.error);
        });
    }

    /**
     * Clear offline cart (after sync)
     */
    async clearOfflineCart() {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction('cart', 'readwrite');
            const store = tx.objectStore('cart');
            const clearRequest = store.clear();

            clearRequest.onsuccess = () => {
                console.log('✅ Offline cart cleared');
                resolve();
            };
            clearRequest.onerror = () => reject(clearRequest.error);
        });
    }

    /**
     * Clear all offline data (for testing/debugging)
     */
    async clearAllData() {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(['products', 'inventory', 'pendingSales', 'cart'], 'readwrite');
            tx.objectStore('products').clear();
            tx.objectStore('inventory').clear();
            tx.objectStore('pendingSales').clear();
            tx.objectStore('cart').clear();

            tx.oncomplete = () => {
                this.pendingSalesCount = 0;
                this.updateUI();
                console.log('✅ Offline data cleared');
                resolve();
            };
            tx.onerror = () => reject(tx.error);
        });
    }

    /**
     * Get offline status
     */
    getStatus() {
        return {
            isOnline: this.isOnline,
            pendingSalesCount: this.pendingSalesCount,
            syncInProgress: this.syncInProgress
        };
    }

    /**
     * Set up idle detection for auto-logout after 10 minutes
     */
    setupIdleDetection() {
        const events = ['mousedown', 'keydown', 'scroll', 'touchstart', 'click', 'wheel', 'mousemove', 'change', 'input', 'submit', 'focus'];
        
        const resetIdleTimer = (eventType) => {
            const timeSinceLastActivity = Date.now() - this.lastActivityTime;
            this.lastActivityTime = Date.now();
            clearTimeout(this.idleTimer);
            
            if (timeSinceLastActivity > 1000) { // Only log if more than 1 second has passed
                console.log(`📱 Activity: ${eventType} (was idle for ${(timeSinceLastActivity / 1000).toFixed(1)}s). Resetting 10-minute idle timer.`);
            }
            
            // Check every 30 seconds if user is idle
            this.idleTimer = setTimeout(() => this.checkIdleTimeout(), 30000);
        };
        
        // Listen for user activity with event type logging
        events.forEach(event => {
            document.addEventListener(event, (e) => resetIdleTimer(e.type), true);
        });
        
        // Track form submissions and clicks on links in admin
        document.addEventListener('beforeunload', () => {
            this.lastActivityTime = Date.now();
            console.log('🔄 Page navigation detected - activity recorded');
        });
        
        // Also track form submissions
        document.addEventListener('submit', () => {
            this.lastActivityTime = Date.now();
            console.log('📤 Form submission detected - activity recorded');
        });
        
        // Track AJAX/Fetch requests
        if (window.fetch) {
            const originalFetch = window.fetch;
            window.fetch = function(...args) {
                this.lastActivityTime = Date.now();
                console.log('🌐 AJAX request detected - activity recorded');
                return originalFetch.apply(this, args);
            }.bind(this);
        }
        
        // Track XMLHttpRequest
        const originalOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(...args) {
            this.addEventListener('loadstart', () => {
                offlineManager.lastActivityTime = Date.now();
                console.log('🌐 XMLHttpRequest detected - activity recorded');
            });
            return originalOpen.apply(this, args);
        };
        
        console.log('✅ Idle detection initialized - will auto-logout after 10 minutes of inactivity');
        console.log('📡 Tracking: mouse, keyboard, scroll, touch, AJAX, forms, page navigation');
        
        // Initial check
        this.checkIdleTimeout();
    }

    /**
     * Check if session has timed out due to inactivity
     */
    checkIdleTimeout() {
        const timeSinceLastActivity = Date.now() - this.lastActivityTime;
        const idleMinutes = (timeSinceLastActivity / 60000).toFixed(2);
        const maxMinutes = (this.IDLE_TIMEOUT / 60000).toFixed(0);
        
        if (timeSinceLastActivity >= this.IDLE_TIMEOUT) {
            console.error(`⏱️ SESSION EXPIRED: No activity for ${idleMinutes} minutes (max: ${maxMinutes} min). Logging out...`);
            this.logoutUser();
        } else {
            // Log remaining time every check
            const remainingMs = this.IDLE_TIMEOUT - timeSinceLastActivity;
            const remainingMin = (remainingMs / 60000).toFixed(2);
            console.log(`⏰ Session active - ${idleMinutes} min idle, ${remainingMin} min remaining before logout`);
            
            // Also verify server-side session is still valid (every 2 minutes)
            if (Math.random() < 0.1) { // 10% chance on each check
                this.verifyServerSession();
            }
            
            // Schedule next check
            const timeUntilTimeout = this.IDLE_TIMEOUT - timeSinceLastActivity;
            this.idleTimer = setTimeout(() => this.checkIdleTimeout(), Math.min(timeUntilTimeout, 30000));
        }
    }

    /**
     * Verify session is still valid on server side
     */
    async verifyServerSession() {
        try {
            const response = await fetch('/account/api/session-check/', {
                method: 'GET',
                credentials: 'include'
            });
            
            if (response.status === 401 || response.status === 403) {
                console.error('❌ Server session expired - logging out');
                this.logoutUser();
            } else if (response.ok) {
                const data = await response.json();
                if (!data.authenticated) {
                    console.error('❌ Server says not authenticated - logging out');
                    this.logoutUser();
                } else {
                    console.log('✓ Server session verified as valid');
                }
            }
        } catch (error) {
            console.warn('⚠️ Could not verify session with server:', error.message);
            // Don't logout on network errors, just continue
        }
    }

    /**
     * Log out the user by redirecting to login
     */
    logoutUser() {
        // Clear offline data to prevent stale state
        console.log('🚪 Clearing session and redirecting to login...');
        
        // Redirect to logout URL
        window.location.href = '/account/logout/';
    }
}

// Initialize globally
const offlineManager = new OfflineManager();
