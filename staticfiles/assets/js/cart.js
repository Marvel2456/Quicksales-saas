// Get CSRF token from meta tag (since CSRF_COOKIE_HTTPONLY=True blocks cookie access)
const csrftoken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

let updateCart = document.getElementsByClassName('add-cart')

for (let i = 0; i < updateCart.length; i++) {
    updateCart[i].addEventListener('click', function(e){
        e.preventDefault()
        let inventoryId = this.dataset.inventory
        let action = this.dataset.action
        let url = this.dataset.url

        console.log('inventoryId:', inventoryId, 'action:', action, 'url:', url)
        console.log('csrftoken:', csrftoken)
        
        UpdateUserCart(inventoryId, action, url)
    })
}

function UpdateUserCart(inventoryId, action, url){
    console.log('UpdateUserCart called with:', {inventoryId, action, url, csrftoken})

    if (!navigator.onLine) {
        console.warn('📡 Offline: Intercepted cart update action');
        if (window.offlineManager) {
            window.offlineManager.addCartItemOffline(inventoryId);
        } else {
            showNotification('Offline manager not initialized.', true);
        }
        return;
    }

    if (!csrftoken) {
        console.error('❌ CSRF token not found')
        showNotification('Security error: CSRF token missing. Please refresh the page.', true)
        return
    }

    fetch(url, {
        method:'POST',
        credentials: 'include',
        headers:{
            'Content-Type':'application/json',
            'X-CSRFToken': csrftoken,
        },
        body:JSON.stringify({'inventoryId':inventoryId, 'action':action})
    })
    .then(res => {
        console.log('Response status:', res.status)
        if (!res.ok) {
            return res.text().then(text => {
                throw new Error(`HTTP ${res.status}: ${text}`)
            })
        }
        return res.json()
    })
    .then((data) =>{
        console.log('Cart data:', data)
        if (data.error) {
            showNotification(data.error, true)
            return
        }
        // Update cart count if element exists
        const cartBadge = document.getElementById('addCart')
        if (cartBadge) {
            cartBadge.innerHTML = `${data.qty}`
        }
        // Show success notification
        showNotification('Item added to cart successfully')
    })
    .catch((error) => {
        console.error('❌ Cart update failed:', error);
        showNotification(`Failed to add item to cart: ${error.message}`, true);
    });
}

function showNotification(message, isError = false) {
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
    }, 3000);
}

// Quantity update handler
let inputfields = document.getElementsByClassName('Qty')
for(let i = 0; i < inputfields.length; i++){
    inputfields[i].addEventListener('change', updateQuantity)   
}

function updateQuantity(e){
    let inputvalue = e.target.value
    let inventoryId = e.target.dataset.inventory
    let url = e.target.dataset.url

    const data = {invent_id: inventoryId, val: inputvalue};

    fetch(url, {
        method:'POST',
        credentials: 'include',
        headers:{
            'Content-Type':'application/json',
            'X-CSRFToken':csrftoken,
        },
        body:JSON.stringify(data)
    })
    .then(res => {
        if (!res.ok) {
            return res.text().then(text => {
                throw new Error(`HTTP ${res.status}: ${text}`)
            })
        }
        return res.json()
    })
    .then((data) =>{
        console.log('Success:', data);
        // Update the specific subtotal for this inventory item
        const subTotalElement = document.getElementById(`sub_total_${inventoryId}`);
        if (subTotalElement) {
            subTotalElement.innerHTML = `${data.sub_total.toFixed(2)}`
        }
        // Update the cart totals
        document.getElementById('final_total').innerHTML = `<b>Total:</b><div><i class="fa-solid fa-naira-sign"></i>${data.final_total.toFixed(2)}</div>`
        document.getElementById('sum_quantity').innerHTML = `<b>Item:</b><div>${data.total_quantity}</div>`
        document.getElementById('addCart').innerHTML = `${data.total_quantity}`
        showNotification('Quantity updated successfully')
    })
    .catch((error) => {
        console.error('❌ Quantity update failed:', error);
        showNotification(`Failed to update quantity: ${error.message}`, true);
    });
}
// Delete item from cart handler
let deleteButtons = document.getElementsByClassName('delete-item')
for(let i = 0; i < deleteButtons.length; i++){
    deleteButtons[i].addEventListener('click', deleteCartItem)   
}

function deleteCartItem(e){
    e.preventDefault()
    let inventoryId = e.target.closest('button').dataset.inventory
    let url = e.target.closest('button').dataset.url

    const data = {invent_id: inventoryId};

    fetch(url, {
        method:'POST',
        credentials: 'include',
        headers:{
            'Content-Type':'application/json',
            'X-CSRFToken':csrftoken,
        },
        body:JSON.stringify(data)
    })
    .then(res => {
        if (!res.ok) {
            return res.text().then(text => {
                throw new Error(`HTTP ${res.status}: ${text}`)
            })
        }
        return res.json()
    })
    .then((data) =>{
        console.log('Item deleted successfully:', data);
        // Remove the product row from the DOM
        const productRow = e.target.closest('.row');
        const hrElement = productRow.nextElementSibling;
        productRow.remove();
        if (hrElement && hrElement.tagName === 'HR') {
            hrElement.remove();
        }
        
        // Update the cart totals
        document.getElementById('final_total').innerHTML = `<b>Total:</b><div><i class="fa-solid fa-naira-sign"></i>${data.final_total.toFixed(2)}</div>`
        document.getElementById('sum_quantity').innerHTML = `<b>Item:</b><div>${data.total_quantity}</div>`
        document.getElementById('addCart').innerHTML = `${data.total_quantity}`
        showNotification('Item removed from cart successfully')
    })
    .catch((error) => {
        console.error('❌ Delete failed:', error);
        showNotification(`Failed to remove item from cart: ${error.message}`, true);
    });
}