/**
 * Quicksales Offline Cart and Checkout Display
 * Renders IndexedDB cart state and handles local checkouts.
 */

class OfflineCartDisplay {
    constructor() {
        this.branchId = window.BRANCH_ID;
        this.isCheckout = window.IS_CHECKOUT_PAGE;
        this.db = null;
        
        this.init();
    }

    async init() {
        const container = document.getElementById('offlineContentContainer');
        try {
            // Wait for offlineManager to establish database connection
            this.db = await this.getDBConnection();
            await this.render();
        } catch (error) {
            console.error('❌ OfflineCartDisplay: Init failed:', error);
            if (container) {
                container.innerHTML = `
                    <div class="card border-0 shadow-sm p-4 text-center">
                        <div class="text-warning mb-3"><i class="fa-solid fa-triangle-exclamation fa-3x"></i></div>
                        <h5>Could not load offline cart</h5>
                        <p class="text-muted">${error.message || 'The local database could not be opened. Make sure you have visited the store page while online at least once.'}</p>
                        <div class="mt-3">
                            <a href="/ims/store/${this.branchId}/" class="btn btn-primary" style="background-color: #02296e; border-color: #02296e;">Back to Store</a>
                            <button class="btn btn-outline-secondary ms-2" onclick="location.reload()">Retry</button>
                        </div>
                    </div>
                `;
            }
        }
    }

    getDBConnection() {
        return new Promise((resolve, reject) => {
            let resolved = false;
            const check = setInterval(() => {
                if (window.offlineManager && window.offlineManager.db) {
                    if (!resolved) {
                        resolved = true;
                        clearInterval(check);
                        resolve(window.offlineManager.db);
                    }
                }
            }, 50);
            
            // Timeout after 10 seconds to prevent infinite polling
            setTimeout(() => {
                if (!resolved) {
                    resolved = true;
                    clearInterval(check);
                    reject(new Error('Database connection timed out. Please reload the page.'));
                }
            }, 10000);
        });
    }

    async render() {
        const container = document.getElementById('offlineContentContainer');
        if (!container) return;

        try {
            // Display offline elements and hide online elements
            const onlineSalesGroup = document.getElementById('onlineSalesGroup');
            const onlineButtons = document.getElementById('onlineButtons');
            const offlineSalesGroup = document.getElementById('offlineSalesGroup');
            const offlineButtons = document.getElementById('offlineButtons');
            const offlineSalesCard = document.getElementById('offlineSalesCard');
            
            if (onlineSalesGroup) onlineSalesGroup.style.display = 'none';
            if (onlineButtons) onlineButtons.style.display = 'none';
            
            if (offlineSalesCard) {
                // Show switcher card on Cart page, hide it on Checkout/Receipt page
                offlineSalesCard.style.display = (this.isCheckout) ? 'none' : 'block';
            }
            if (offlineSalesGroup) offlineSalesGroup.style.display = 'block';
            if (offlineButtons) {
                offlineButtons.style.display = 'block';
            }

            // Get offline cart
            const cart = await window.offlineManager.getActiveOfflineSale();
            const sales = await window.offlineManager.getAllOfflineSales();
            
            // Render open offline sales sessions in switcher
            let salesHtml = '';
            sales.forEach((s, idx) => {
                const isActive = s.id === cart.id;
                const itemsCount = s.items.reduce((sum, item) => sum + item.quantity, 0);
                salesHtml += `
                    <button class="btn btn-sm ${isActive ? 'btn-primary text-white' : 'btn-outline-primary'} offline-switch-sale-btn me-1 mb-1" data-sale-id="${s.id}">
                        Sale #${idx + 1}
                        ${itemsCount > 0 ? `<span class="badge bg-light text-dark ms-1">${itemsCount} items</span>` : ''}
                    </button>
                `;
            });
            if (offlineSalesGroup) {
                offlineSalesGroup.innerHTML = salesHtml;
                offlineSalesGroup.querySelectorAll('.offline-switch-sale-btn').forEach(btn => {
                    btn.addEventListener('click', async () => {
                        const saleId = btn.dataset.saleId;
                        sessionStorage.setItem(`active_offline_sale_${this.branchId}`, saleId);
                        const activeSale = await window.offlineManager.getActiveOfflineSale();
                        window.offlineManager.updateCartBadgeCount(activeSale);
                        this.render();
                    });
                });
            }

            // Bind offline actions
            const newSaleBtn = document.getElementById('offlineNewSaleBtn');
            if (newSaleBtn && !newSaleBtn.dataset.bound) {
                newSaleBtn.dataset.bound = 'true';
                newSaleBtn.addEventListener('click', async () => {
                    await window.offlineManager.createOfflineSale();
                    const activeSale = await window.offlineManager.getActiveOfflineSale();
                    window.offlineManager.updateCartBadgeCount(activeSale);
                    this.render();
                });
            }
            
            const cancelBtn = document.getElementById('offlineCancelBtn');
            if (cancelBtn && !cancelBtn.dataset.bound) {
                cancelBtn.dataset.bound = 'true';
                cancelBtn.addEventListener('click', async () => {
                    const activeSale = await window.offlineManager.getActiveOfflineSale();
                    if (confirm('Are you sure you want to cancel the current sale session?')) {
                        await window.offlineManager.cancelOfflineSale(activeSale.id);
                        const newActiveSale = await window.offlineManager.getActiveOfflineSale();
                        window.offlineManager.updateCartBadgeCount(newActiveSale);
                        this.render();
                    }
                });
            }
            
            // Enrich cart items with catalog data
            const enrichedItems = [];
            let totalCartAmount = 0;
            let totalCartItems = 0;

            for (const cartItem of cart.items) {
                const catalogItem = await window.offlineManager.getFromStore('catalog', cartItem.inventory_id);
                if (catalogItem) {
                    const totalItemPrice = catalogItem.sale_price * cartItem.quantity;
                    totalCartAmount += totalItemPrice;
                    totalCartItems += cartItem.quantity;
                    
                    enrichedItems.push({
                        id: cartItem.inventory_id,
                        name: catalogItem.product_name,
                        price: catalogItem.sale_price,
                        maxQuantity: catalogItem.store_quantity,
                        quantity: cartItem.quantity,
                        total: totalItemPrice
                    });
                }
            }

            if (this.isCheckout) {
                this.renderCheckout(container, enrichedItems, totalCartAmount, totalCartItems);
            } else {
                this.renderCart(container, enrichedItems, totalCartAmount, totalCartItems);
            }
        } catch (error) {
            console.error('❌ OfflineCartDisplay: Render failed:', error);
            container.innerHTML = `<div class="alert alert-danger">Error loading local database: ${error.message}</div>`;
        }
    }

    renderCart(container, items, totalAmount, totalItems) {
        if (items.length === 0) {
            container.innerHTML = `
                <div class="card border-0 shadow-sm p-5 text-center">
                    <div class="text-muted mb-3"><i class="fa-solid fa-cart-shopping fa-3x" style="color: #bcc1cb;"></i></div>
                    <h4>Your Offline Cart is empty</h4>
                    <p class="text-muted">Return to the product listing to add items to your cart.</p>
                    <div class="mt-4">
                        <a href="/ims/store/${this.branchId}/" class="btn btn-primary" style="background-color: #02296e; border-color: #02296e;">Back to Store</a>
                    </div>
                </div>
            `;
            return;
        }

        let tableRows = '';
        for (const item of items) {
            tableRows += `
                <div class="row align-items-center py-3 border-bottom text-muted">
                    <div class="col-12 col-md-5 mb-2 mb-md-0 text-dark font-weight-bold">
                        <span style="font-size: 1.05rem;">${item.name}</span>
                    </div>
                    <div class="col-4 col-md-2">
                        <span>₦${item.price.toFixed(2)}</span>
                    </div>
                    <div class="col-5 col-md-3">
                        <div class="input-group input-group-sm" style="max-width: 120px;">
                            <input type="number" class="form-control qty-input" 
                                   value="${item.quantity}" 
                                   min="1" 
                                   max="${item.maxQuantity}" 
                                   data-id="${item.id}">
                            <span class="input-group-text" style="font-size: 0.75rem;">max ${item.maxQuantity}</span>
                        </div>
                    </div>
                    <div class="col-3 col-md-2 text-end text-dark font-weight-bold">
                        <span>₦${item.total.toFixed(2)}</span>
                        <button class="btn btn-sm btn-outline-danger border-0 ms-2 delete-btn" data-id="${item.id}">
                            <i class="fa-solid fa-trash"></i>
                        </button>
                    </div>
                </div>
            `;
        }

        container.innerHTML = `
            <div class="card border-0 shadow-sm mb-4">
                <div class="card-header bg-white py-3 border-bottom-0">
                    <h5 class="m-0 text-dark">Local Offline Cart (${totalItems} items)</h5>
                </div>
                <div class="card-body py-0">
                    ${tableRows}
                </div>
                <div class="card-footer bg-white py-4 d-flex justify-content-between align-items-center">
                    <div>
                        <span class="text-muted" style="font-size: 0.9rem;">Grand Total:</span>
                        <h3 class="m-0 text-dark font-weight-bold">₦${totalAmount.toFixed(2)}</h3>
                    </div>
                    <div>
                        <a href="/ims/store/${this.branchId}/" class="btn btn-outline-secondary me-2">Back</a>
                        <a href="/ims/checkout/${this.branchId}/" class="btn btn-success" style="background-color: #02296e; border-color: #02296e; padding: 8px 20px;">Checkout</a>
                    </div>
                </div>
            </div>
        `;

        this.addCartEventListeners();
    }

    addCartEventListeners() {
        // Change quantity
        const qtyInputs = document.querySelectorAll('.qty-input');
        qtyInputs.forEach(input => {
            input.addEventListener('change', async (e) => {
                const itemId = e.target.dataset.id;
                let val = parseInt(e.target.value) || 1;
                const max = parseInt(e.target.getAttribute('max'));
                
                if (val < 1) val = 1;
                if (val > max) {
                    val = max;
                    window.offlineManager.showNotification(`Only ${max} units available in stock.`, true);
                }
                
                e.target.value = val;
                
                const cart = await window.offlineManager.getActiveOfflineSale();
                const item = cart.items.find(i => i.inventory_id === itemId);
                if (item) {
                    item.quantity = val;
                    await window.offlineManager.saveToStore('offline_sales', cart);
                    this.render();
                }
            });
        });

        // Delete item
        const deleteButtons = document.querySelectorAll('.delete-btn');
        deleteButtons.forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const itemId = e.currentTarget.dataset.id;
                const cart = await window.offlineManager.getActiveOfflineSale();
                cart.items = cart.items.filter(i => i.inventory_id !== itemId);
                await window.offlineManager.saveToStore('offline_sales', cart);
                window.offlineManager.showNotification('Item removed from offline cart.');
                this.render();
            });
        });
    }

    renderCheckout(container, items, totalAmount, totalItems) {
        let itemSummaries = '';
        for (const item of items) {
            itemSummaries += `
                <div class="d-flex justify-content-between py-2 border-bottom text-muted">
                    <span>${item.name} (x${item.quantity})</span>
                    <span class="text-dark">₦${item.total.toFixed(2)}</span>
                </div>
            `;
        }

        container.innerHTML = `
            <div class="row g-4">
                <div class="col-12 col-lg-8">
                    <div class="card border-0 shadow-sm p-4">
                        <h5 class="mb-4">Order Summary</h5>
                        ${itemSummaries}
                        <div class="d-flex justify-content-between py-3 font-weight-bold" style="font-size: 1.2rem;">
                            <span>Total Amount</span>
                            <span class="text-dark">₦${totalAmount.toFixed(2)}</span>
                        </div>
                    </div>
                </div>
                
                <div class="col-12 col-lg-4">
                    <div class="card border-0 shadow-sm p-4">
                        <h5 class="mb-4">Payment & Confirmation</h5>
                        <form id="offlineCheckoutForm">
                            <div class="mb-4">
                                <label for="method" class="form-label font-weight-bold">Select Payment Method</label>
                                <select id="method" name="method" class="form-select" required>
                                    <option value="" disabled selected>Select Method</option>
                                    <option value="Cash">Cash</option>
                                    <option value="Transfer">Transfer</option>
                                    <option value="POS">POS Card Reader</option>
                                </select>
                            </div>
                            
                            <button type="submit" class="btn btn-success w-100 py-3" style="background-color: #02296e; border-color: #02296e; font-weight: 600;">
                                Confirm Payment (Offline)
                            </button>
                            
                            <a href="/ims/cart/${this.branchId}/" class="btn btn-outline-secondary w-100 mt-2 py-2">
                                Back to Cart
                            </a>
                        </form>
                    </div>
                </div>
            </div>
        `;

        this.addCheckoutEventListeners(items, totalAmount);
    }

    addCheckoutEventListeners(items, totalAmount) {
        const form = document.getElementById('offlineCheckoutForm');
        if (!form) return;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const methodSelect = document.getElementById('method');
            const selectedMethod = methodSelect.value;
            
            if (!selectedMethod) {
                alert('Please select a payment method');
                return;
            }

            const submitBtn = form.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.textContent = 'Processing Locally...';

            try {
                // 1. Generate temp ID and transaction object
                const tempId = 'offline_' + Date.now() + '_' + Math.random().toString(36).substring(2, 11);
                
                const saleItems = items.map(item => ({
                    inventory_id: item.id,
                    quantity: item.quantity
                }));

                const offlineSale = {
                    tempId: tempId,
                    branch_id: this.branchId,
                    items: saleItems,
                    method: selectedMethod,
                    total_cart: totalAmount,
                    date_added: new Date().toISOString()
                };

                // 2. Save transaction to pending_sales store
                await window.offlineManager.saveToStore('pending_sales', offlineSale);

                // 3. Deduct stock quantities locally in catalog cache
                for (const item of items) {
                    const catalogItem = await window.offlineManager.getFromStore('catalog', item.id);
                    if (catalogItem) {
                        catalogItem.store_quantity = Math.max(0, catalogItem.store_quantity - item.quantity);
                        await window.offlineManager.saveToStore('catalog', catalogItem);
                    }
                }

                // 4. Clear branch offline cart
                const activeSale = await window.offlineManager.getActiveOfflineSale();
                await window.offlineManager.cancelOfflineSale(activeSale.id);

                // 5. Render success receipt
                await this.renderReceipt(offlineSale, items, totalAmount);
                window.offlineManager.showNotification('Payment processed successfully. Transaction queued for sync.');

            } catch (error) {
                console.error('❌ OfflineCartDisplay: Checkout failed:', error);
                alert('An error occurred during offline checkout processing: ' + error.message);
                submitBtn.disabled = false;
                submitBtn.textContent = 'Confirm Payment (Offline)';
            }
        });
    }

    async renderReceipt(sale, items, totalAmount) {
        const container = document.getElementById('offlineContentContainer');
        if (!container) return;

        // Fetch branding details from IndexedDB
        const orgLogo = await window.offlineManager.getFromStore('metadata', 'org_logo');
        const orgName = await window.offlineManager.getFromStore('metadata', 'org_name');

        let logoHtml = '';
        if (orgLogo && orgLogo.value) {
            logoHtml = `<img src="${orgLogo.value}" alt="${orgName ? orgName.value : ''}" style="max-height: 80px; margin-bottom: 10px;">`;
        }

        let orgTitleHtml = '';
        if (orgName && orgName.value) {
            orgTitleHtml = `<h2><strong>${orgName.value}</strong></h2>`;
        } else {
            orgTitleHtml = `<h4 class="m-0 font-weight-bold">Offline Sale Confirmed</h4>`;
        }

        const offlineSalesCard = document.getElementById('offlineSalesCard');
        if (offlineSalesCard) {
            offlineSalesCard.style.display = 'none';
        }

        let itemsHtml = '';
        for (const item of items) {
            itemsHtml += `
                <div class="d-flex justify-content-between py-1 border-bottom-0 text-muted" style="font-size: 0.95rem;">
                    <span>${item.name} (x${item.quantity})</span>
                    <span>₦${item.total.toFixed(2)}</span>
                </div>
            `;
        }

        container.innerHTML = `
            <div class="card border-0 shadow-sm p-4 mx-auto text-center" style="max-width: 550px;">
                <div class="py-4 border-bottom mb-4">
                    ${logoHtml}
                    ${orgTitleHtml}
                    <p class="text-muted m-0 mt-1">Transaction recorded locally</p>
                </div>
                
                <div class="mb-4 text-start">
                    <h6 class="font-weight-bold text-dark mb-3">Receipt Details</h6>
                    <div class="d-flex justify-content-between mb-2">
                        <span class="text-muted">Temp Sync ID:</span>
                        <code class="text-dark">${sale.tempId}</code>
                    </div>
                    <div class="d-flex justify-content-between mb-2">
                        <span class="text-muted">Date/Time:</span>
                        <span class="text-dark">${new Date(sale.date_added).toLocaleString()}</span>
                    </div>
                    <div class="d-flex justify-content-between mb-2">
                        <span class="text-muted">Payment Method:</span>
                        <span class="badge bg-secondary">${sale.method}</span>
                    </div>
                </div>
                
                <div class="border-top border-bottom py-3 mb-4 text-start">
                    <h6 class="font-weight-bold text-dark mb-2">Purchased Items</h6>
                    ${itemsHtml}
                    <div class="d-flex justify-content-between font-weight-bold mt-3 text-dark" style="font-size: 1.15rem;">
                        <span>Paid Total</span>
                        <span>₦${totalAmount.toFixed(2)}</span>
                    </div>
                </div>

                <div class="alert alert-warning-subtle border border-warning text-warning-emphasis p-3 text-center mb-4 d-print-none" style="font-size: 0.85rem; border-radius: 6px;">
                    <i class="fa-solid fa-cloud-arrow-up me-1"></i> Transaction queued. Will sync automatically once internet returns.
                </div>
                
                <div class="row g-2 d-print-none">
                    <div class="col-6">
                        <button onclick="window.print()" class="btn btn-outline-secondary w-100">
                            <i class="fa-solid fa-print me-1"></i> Print Receipt
                        </button>
                    </div>
                    <div class="col-6">
                        <a href="/ims/store/${this.branchId}/" class="btn btn-primary w-100" style="background-color: #02296e; border-color: #02296e;">
                            New Order
                        </a>
                    </div>
                </div>
            </div>
        `;
    }
}

function initOfflineCart() {
    if (document.getElementById('offlineContentContainer')) {
        new OfflineCartDisplay();
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initOfflineCart);
} else {
    initOfflineCart();
}
