/**
 * Checkout Handler - Handles online checkout
 */

class CheckoutHandler {
    constructor() {
        this.branchId = this.getBranchIdFromUrl();
        this.init();
    }

    init() {
        this.setupCheckout();
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
            console.warn('Complete button not found');
        }
    }

    async handleCheckout(event, button) {
        event.preventDefault();
        console.log('Proceeding with checkout');
        button.closest('form').submit();
    }

    showNotification(message, isError = false) {
        const alertDiv = document.createElement('div');
        alertDiv.className = isError ? 'alert alert-danger' : 'alert alert-success';
        alertDiv.textContent = message;
        alertDiv.style.position = 'fixed';
        alertDiv.style.top = '80px';
        alertDiv.style.right = '20px';
        alertDiv.style.zIndex = '10000';
        alertDiv.style.maxWidth = '300px';
        document.body.appendChild(alertDiv);
        
        setTimeout(() => {
            alertDiv.remove();
        }, 3000);
    }
}

// Initialize checkout handler when page loads
document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname.includes('/checkout/')) {
        new CheckoutHandler();
    }
});
