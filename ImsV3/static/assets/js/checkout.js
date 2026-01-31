/**
 * Checkout Handler - Handles both online and offline checkout
 * Saves pending sales to IndexedDB when offline
 */

class CheckoutHandler {
    constructor() {
        this.branchId = this.getBranchIdFromUrl();
        this.init();
    }

    init() {
        // Wait for offline manager to be ready
        const checkInterval = setInterval(() => {
            if (typeof offlineManager !== 'undefined' && offlineManager.db) {
                clearInterval(checkInterval);
                this.setupCheckout();
            }
        }, 100);
    }

    getBranchIdFromUrl() {
        // Extract branch ID from URL like /checkout/UUID/
        const pathParts = window.location.pathname.split('/');
        return pathParts[pathParts.length - 2];
    }

    setupCheckout() {
        const completeButton = document.querySelector('button[data-action="complete-sale"]') || 
                               document.querySelector('form button[type="submit"]') ||
                               document.getElementById('pay');
        
        if (completeButton) {
            completeButton.addEventListener('click', (e) => this.handleCheckout(e, completeButton));
        } else {
            console.warn('⚠️ Complete button not found');
        }
    }

    async handleCheckout(event, button) {
        event.preventDefault();
        
        // Check if offline
        if (!navigator.onLine) {
            await this.handleOfflineCheckout();
            return;
        }

        // Online - proceed normally
        console.log('✅ Online - proceeding with normal checkout');
        button.closest('form').submit();
    }

    async handleOfflineCheckout() {
        try {
            console.log('⚠️ Offline checkout initiated');
            
            // Get cart items from offline manager
            const cartItems = await offlineManager.getOfflineCart();
            
            if (!cartItems || cartItems.length === 0) {
                this.showNotification('Cart is empty', true);
                return;
            }

            // Enrich cart items with product info from database
            const enrichedItems = await this.enrichCartItems(cartItems);

            // Get payment method from form
            const paymentMethodSelect = document.querySelector('select[name="payment_method"]');
            const paymentMethod = paymentMethodSelect?.value || 'cash';
            
            // Calculate total from cart items
            const total = await this.calculateTotal(enrichedItems);

            // Create pending sale with full item details
            const pendingSale = {
                cartItems: enrichedItems,
                paymentMethod: paymentMethod,
                total: total,
                branchId: this.branchId,
                timestamp: new Date().toISOString(),
                status: 'pending_checkout',
                source: 'offline'
            };

            // Save as pending sale
            const tempId = await offlineManager.savePendingSale(pendingSale);

            console.log('✅ Sale queued for sync:', pendingSale);
            
            // Clear offline cart after saving
            await offlineManager.clearOfflineCart();

            // Show success message
            this.showNotification('Order saved offline. Will sync when you come back online.', false);

            // Redirect to store after 2 seconds
            setTimeout(() => {
                window.location.href = `/ims/store/${this.branchId}/`;
            }, 2000);

        } catch (error) {
            console.error('❌ Offline checkout failed:', error);
            this.showNotification('Failed to save order', true);
        }
    }

    async enrichCartItems(cartItems) {
        // Get inventory data from offline manager
        const enrichedItems = [];
        
        for (const item of cartItems) {
            try {
                const inventory = await offlineManager.getCachedInventory(item.inventoryId);
                if (inventory) {
                    const salePrice = inventory.sale_price ?? inventory.cost_price ?? 0;
                    const costPrice = inventory.cost_price ?? 0;
                    enrichedItems.push({
                        inventoryId: item.inventoryId,
                        quantity: item.quantity,
                        productName: inventory.product_name || 'Unknown',
                        unitPrice: salePrice,
                        cost_price: costPrice,
                        product_id: inventory.product_id,
                        inventory: inventory
                    });
                    console.log('✅ Enriched item:', item.inventoryId, 'product_id:', inventory.product_id);
                } else {
                    console.warn('⚠️ Inventory not found in cache for:', item.inventoryId);
                    enrichedItems.push({
                        ...item,
                        product_id: item.inventoryId  // Will be used for error identification
                    });
                }
            } catch (error) {
                console.warn('❌ Could not enrich item:', item.inventoryId, error);
                enrichedItems.push({
                    ...item,
                    product_id: item.inventoryId  // Will be used for error identification
                });
            }
        }
        
        return enrichedItems;
    }

    async calculateTotal(items) {
        return items.reduce((sum, item) => {
            const unitPrice = item.unitPrice || 0;
            return sum + (unitPrice * item.quantity);
        }, 0);
    }

    extractTotal(text) {
        if (!text) return 0;
        // Extract number from text like "Total: 1,234.50"
        const match = text.match(/[\d,]+\.?\d*/);
        return match ? parseFloat(match[0].replace(/,/g, '')) : 0;
    }

    showNotification(message, isError = false) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${isError ? 'danger' : 'success'}`;
        alertDiv.textContent = message;
        alertDiv.style.cssText = `
            position: fixed;
            top: 100px;
            right: 20px;
            z-index: 10000;
            max-width: 400px;
            padding: 15px;
            border-radius: 4px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        `;
        document.body.appendChild(alertDiv);
        
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }
}

// Initialize checkout handler when page loads
document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname.includes('/checkout/')) {
        new CheckoutHandler();
    }
});

// Also initialize if DOM is already loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        if (window.location.pathname.includes('/checkout/')) {
            new CheckoutHandler();
        }
    });
} else {
    if (window.location.pathname.includes('/checkout/')) {
        new CheckoutHandler();
    }
}
