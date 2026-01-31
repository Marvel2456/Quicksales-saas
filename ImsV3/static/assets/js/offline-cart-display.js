/**
 * Offline Cart Display Handler
 * Shows cached cart items when offline
 */

class OfflineCartDisplay {
    constructor() {
        this.branchId = this.getBranchIdFromUrl();
        console.log('🛒 OfflineCartDisplay initialized. Offline:', !navigator.onLine, 'BranchId:', this.branchId);
        this.init();
    }

    getBranchIdFromUrl() {
        // Extract branch ID from URL like /ims/cart/UUID/
        const pathParts = window.location.pathname.split('/');
        return pathParts[pathParts.length - 2];
    }

    async init() {
        // Check if we're on cart or checkout page
        const isCartPage = window.location.pathname.includes('/cart/');
        const isCheckoutPage = window.location.pathname.includes('/checkout/');
        
        if (!(isCartPage || isCheckoutPage)) {
            console.log('Not a cart/checkout page, skipping display');
            return;
        }
        
        console.log('🛒 Cart/Checkout page detected. Offline:', !navigator.onLine);
        
        // Check if this is the offline template (if offlineCartContainer exists, we're definitely on offline page)
        const offlineContainer = document.getElementById('offlineCartContainer');
        const isOfflineTemplate = !!offlineContainer;
        
        if (isOfflineTemplate) {
            console.log('✅ On offline template - forcing cart display regardless of navigator.onLine');
            // Always display when on offline template
            await this.displayOfflineCartDirect();
        } else {
            // Only try to display if actually offline
            if (!navigator.onLine) {
                await this.displayOfflineCart();
            }
        }
    }
    
    async displayOfflineCartDirect() {
        // Open DB directly without relying on offlineManager
        try {
            console.log('📦 Opening DB directly for offline cart...');
            const db = await this.openDatabase();
            const cartItems = await this.getCartItemsFromDB(db);
            
            console.log('Cart items from DB:', cartItems);
            
            if (!cartItems || cartItems.length === 0) {
                this.showEmptyCart();
                return;
            }
            
            const enrichedItems = await this.enrichCartItemsFromDB(cartItems, db);
            this.createOfflineCartDisplay(enrichedItems);
        } catch (error) {
            console.error('❌ Error displaying offline cart directly:', error);
            this.showEmptyCart();
        }
    }
    
    openDatabase() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open('quicksales_offline', 1);
            
            request.onerror = () => {
                console.error('Failed to open DB:', request.error);
                reject(request.error);
            };
            
            request.onsuccess = () => {
                console.log('✅ DB opened directly');
                resolve(request.result);
            };
        });
    }
    
    getCartItemsFromDB(db) {
        return new Promise((resolve, reject) => {
            const transaction = db.transaction(['cart'], 'readonly');
            const store = transaction.objectStore('cart');
            const request = store.getAll();
            
            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(request.result);
        });
    }
    
    async enrichCartItemsFromDB(cartItems, db) {
        const enrichedItems = [];
        
        for (const item of cartItems) {
            try {
                const inventory = await this.getInventoryFromDBDirect(item.inventoryId, db);
                
                if (inventory) {
                    enrichedItems.push({
                        id: item.id || item.inventoryId,
                        inventoryId: item.inventoryId,
                        quantity: item.quantity || 1,
                        productName: inventory.product_name || 'Unknown Product',
                        unitPrice: inventory.cost_price || inventory.selling_price || 0,
                        inventory: inventory
                    });
                } else {
                    enrichedItems.push({
                        id: item.inventoryId,
                        inventoryId: item.inventoryId,
                        quantity: item.quantity || 1,
                        productName: 'Product',
                        unitPrice: 0
                    });
                }
            } catch (error) {
                console.warn('Error enriching item:', error);
                enrichedItems.push({
                    id: item.inventoryId,
                    inventoryId: item.inventoryId,
                    quantity: item.quantity || 1,
                    productName: 'Product',
                    unitPrice: 0
                });
            }
        }
        
        return enrichedItems;
    }
    
    getInventoryFromDBDirect(inventoryId, db) {
        return new Promise((resolve) => {
            const transaction = db.transaction(['inventory'], 'readonly');
            const store = transaction.objectStore('inventory');
            const request = store.get(inventoryId);
            
            request.onerror = () => resolve(null);
            request.onsuccess = () => resolve(request.result);
        });
    }

    async displayOfflineCart() {
        console.log('📦 Starting displayOfflineCart...');
        
        try {
            // Get cart items from IndexedDB
            const cartItems = await offlineManager.getOfflineCart();
            
            console.log('Cart items from DB:', cartItems);
            
            if (!cartItems || cartItems.length === 0) {
                this.showEmptyCart();
                return;
            }

            // Enrich items with product info
            const enrichedItems = await this.enrichCartItems(cartItems);
            console.log('Enriched items:', enrichedItems);

            // Clear existing content and create a new display
            this.createOfflineCartDisplay(enrichedItems);

        } catch (error) {
            console.error('❌ Error displaying offline cart:', error);
            this.showEmptyCart();
        }
    }

    async enrichCartItems(cartItems) {
        const enrichedItems = [];
        
        for (const item of cartItems) {
            try {
                const inventory = await this.getInventoryFromDB(item.inventoryId);
                
                if (inventory) {
                    enrichedItems.push({
                        id: item.id || item.inventoryId,
                        inventoryId: item.inventoryId,
                        quantity: item.quantity || 1,
                        productName: inventory.product_name || 'Unknown Product',
                        unitPrice: inventory.cost_price || inventory.selling_price || 0,
                        inventory: inventory
                    });
                } else {
                    console.warn('Inventory not found for:', item.inventoryId);
                    enrichedItems.push({
                        id: item.inventoryId,
                        inventoryId: item.inventoryId,
                        quantity: item.quantity || 1,
                        productName: 'Product',
                        unitPrice: 0
                    });
                }
            } catch (error) {
                console.warn('Could not enrich item:', error);
                enrichedItems.push(item);
            }
        }
        
        return enrichedItems;
    }

    async getInventoryFromDB(inventoryId) {
        return new Promise((resolve) => {
            try {
                const tx = offlineManager.db.transaction('inventory', 'readonly');
                const store = tx.objectStore('inventory');
                const request = store.get(inventoryId);

                request.onsuccess = () => {
                    resolve(request.result);
                };
                request.onerror = () => {
                    console.error('Error fetching inventory:', request.error);
                    resolve(null);
                };
            } catch (error) {
                console.error('Error in getInventoryFromDB:', error);
                resolve(null);
            }
        });
    }

    createOfflineCartDisplay(items) {
        console.log('🎨 Creating offline cart display');
        
        // Try to find container first, fallback to body
        let container = document.getElementById('offlineCartContainer');
        let clearBody = false;
        
        if (!container) {
            container = document.body;
            clearBody = true;
        }
        
        // Clear container content
        if (clearBody) {
            container.innerHTML = '';
        }

        let totalItems = 0;
        let totalPrice = 0;

        const cartHTML = `
            <div class="app-wrapper" style="min-height: 100vh; background: #f5f5f5;">
                <div style="background: white; padding: 20px; border-bottom: 1px solid #ddd;">
                    <div style="max-width: 1200px; margin: 0 auto;">
                        <h3 style="margin: 0;">🛒 Shopping Cart</h3>
                        <small style="color: #666;">Offline Mode - Items will sync when online</small>
                    </div>
                </div>

                <div style="max-width: 1200px; margin: 0 auto; padding: 20px;">
                    <div style="background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; padding: 15px; margin-bottom: 20px;">
                        <i style="color: #ff9800;">⚠️</i> <strong>Offline Mode:</strong> Showing cached cart items
                    </div>
                    
                    <div style="background: white; border-radius: 4px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                        <table style="width: 100%; border-collapse: collapse;">
                            <thead>
                                <tr style="background: #f9f9f9; border-bottom: 2px solid #ddd;">
                                    <th style="padding: 15px; text-align: left; font-weight: 600;">#</th>
                                    <th style="padding: 15px; text-align: left; font-weight: 600;">Product</th>
                                    <th style="padding: 15px; text-align: left; font-weight: 600;">Unit Price</th>
                                    <th style="padding: 15px; text-align: left; font-weight: 600;">Qty</th>
                                    <th style="padding: 15px; text-align: left; font-weight: 600;">Total</th>
                                    <th style="padding: 15px; text-align: center; font-weight: 600;">Action</th>
                                </tr>
                            </thead>
                            <tbody id="offline-cart-tbody">
                            </tbody>
                        </table>
                    </div>

                    <div style="margin-top: 20px; background: white; padding: 20px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <p style="margin: 10px 0;"><strong>Total Items:</strong> <span id="offline-total-items">0</span></p>
                            <p style="margin: 10px 0; font-size: 18px;"><strong>Total Price:</strong> <span style="color: #ff6b35;">₦<span id="offline-total-price">0.00</span></span></p>
                        </div>
                        <div style="display: flex; gap: 10px;">
                            <a href="/ims/store/${this.branchId}/" style="padding: 10px 20px; background: #f0f0f0; color: #333; text-decoration: none; border-radius: 4px; display: inline-block; cursor: pointer;">
                                ← Back to Store
                            </a>
                            <button id="offline-checkout-btn" style="padding: 10px 20px; background: #4CAF50; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 600;">
                                💳 Proceed to Checkout
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        container.innerHTML = cartHTML;

        // Populate table rows
        const tbody = document.getElementById('offline-cart-tbody');
        if (tbody) {
            items.forEach((item, index) => {
                const total = (item.unitPrice * item.quantity).toFixed(2);
                totalItems += item.quantity;
                totalPrice += parseFloat(total);

                const row = document.createElement('tr');
                row.style.borderBottom = '1px solid #eee';
                row.innerHTML = `
                    <td style="padding: 15px;">${index + 1}</td>
                    <td style="padding: 15px;">${item.productName}</td>
                    <td style="padding: 15px;">₦${item.unitPrice.toFixed(2)}</td>
                    <td style="padding: 15px;">
                        <input type="number" 
                               class="offline-qty" 
                               value="${item.quantity}" 
                               data-inventory="${item.inventoryId}"
                               min="1"
                               style="width: 70px; padding: 5px; border: 1px solid #ddd; border-radius: 3px;">
                    </td>
                    <td style="padding: 15px;">₦${total}</td>
                    <td style="padding: 15px; text-align: center;">
                        <button class="offline-remove" 
                                data-inventory="${item.inventoryId}"
                                style="padding: 5px 10px; background: #f44336; color: white; border: none; border-radius: 3px; cursor: pointer;">
                            🗑️
                        </button>
                    </td>
                `;
                tbody.appendChild(row);
            });
        }

        // Update summary
        const itemsEl = document.getElementById('offline-total-items');
        const priceEl = document.getElementById('offline-total-price');
        if (itemsEl) itemsEl.textContent = totalItems;
        if (priceEl) priceEl.textContent = totalPrice.toFixed(2);

        // Add event listeners
        this.addCartEventListeners(items);
    }

    addCartEventListeners(initialItems) {
        // Quantity change handler
        document.querySelectorAll('.offline-qty').forEach(input => {
            input.addEventListener('change', async (e) => {
                const inventoryId = e.target.dataset.inventory;
                const newQty = parseInt(e.target.value);
                
                if (newQty > 0) {
                    await offlineManager.updateCartQuantity(inventoryId, newQty);
                    const items = await offlineManager.getOfflineCart();
                    const enriched = await this.enrichCartItems(items);
                    this.updateCartSummary(enriched);
                    console.log('✅ Quantity updated');
                } else {
                    e.target.value = 1;
                }
            });
        });

        // Remove button handler
        document.querySelectorAll('.offline-remove').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                const inventoryId = e.target.dataset.inventory;
                
                await offlineManager.addToOfflineCart(inventoryId, 'remove');
                
                // Refresh display
                const items = await offlineManager.getOfflineCart();
                
                if (items.length === 0) {
                    this.showEmptyCart();
                } else {
                    const enriched = await this.enrichCartItems(items);
                    this.createOfflineCartDisplay(enriched);
                    this.addCartEventListeners(enriched);
                }
                
                console.log('✅ Item removed from cart');
            });
        });

        // Checkout button
        const checkoutBtn = document.getElementById('offline-checkout-btn');
        if (checkoutBtn) {
            checkoutBtn.addEventListener('click', async () => {
                console.log('📋 Proceeding to offline checkout');
                const items = await offlineManager.getOfflineCart();
                
                if (!items || items.length === 0) {
                    alert('Cart is empty');
                    return;
                }

                // Create and save pending sale
                const enriched = await this.enrichCartItems(items);
                const total = enriched.reduce((sum, item) => sum + (item.unitPrice * item.quantity), 0);

                const pendingSale = {
                    cartItems: enriched,
                    paymentMethod: 'cash',
                    total: total,
                    branchId: this.branchId,
                    timestamp: new Date().toISOString(),
                    status: 'pending_checkout',
                    source: 'offline'
                };

                await offlineManager.savePendingSale(pendingSale);
                await offlineManager.clearOfflineCart();

                alert('✅ Order saved! Will be synced when you come back online.');
                window.location.href = `/ims/store/${this.branchId}/`;
            });
        }
    }

    updateCartSummary(items) {
        let totalItems = 0;
        let totalPrice = 0;

        items.forEach(item => {
            totalItems += item.quantity;
            totalPrice += (item.unitPrice * item.quantity);
        });

        const itemElement = document.getElementById('offline-total-items');
        const totalElement = document.getElementById('offline-total-price');

        if (itemElement) itemElement.textContent = totalItems;
        if (totalElement) totalElement.textContent = totalPrice.toFixed(2);
    }

    showEmptyCart() {
        let container = document.getElementById('offlineCartContainer');
        if (!container) {
            container = document.body;
        }
        
        container.innerHTML = `
            <div class="app-wrapper" style="min-height: 100vh; background: #f5f5f5; display: flex; align-items: center; justify-content: center;">
                <div style="text-align: center; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <p style="font-size: 48px; margin: 20px 0;">🛒</p>
                    <h3 style="margin: 20px 0;">Cart is Empty</h3>
                    <p style="color: #666; margin: 20px 0;">Add items from the store to continue shopping.</p>
                    <a href="/ims/store/${this.branchId}/" style="display: inline-block; padding: 10px 20px; background: #4CAF50; color: white; text-decoration: none; border-radius: 4px; cursor: pointer;">
                        ← Back to Store
                    </a>
                </div>
            </div>
        `;
    }
}

// Initialize when page loads
console.log('offline-cart-display.js loaded');

if (window.location.pathname.includes('/cart/') || 
    window.location.pathname.includes('/checkout/')) {
    console.log('🛒 Cart/Checkout page detected');
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            console.log('DOM loaded, initializing OfflineCartDisplay');
            new OfflineCartDisplay();
        });
    } else {
        console.log('DOM already loaded, initializing OfflineCartDisplay immediately');
        new OfflineCartDisplay();
    }
} else {
    console.log('Not a cart/checkout page');
}
