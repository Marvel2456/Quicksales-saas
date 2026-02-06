let updateCart = document.getElementsByClassName('add-cart')

for (let i = 0; i < updateCart.length; i++) {
    updateCart[i].addEventListener('click', function(){
        let inventoryId = this.dataset.inventory
        let action = this.dataset.action
        let url = this.dataset.url

        console.log('inventoryId:', inventoryId, 'action:', action, 'url:', url)
        
        UpdateUserCart(inventoryId, action, url)
    })
}

function UpdateUserCart(inventoryId, action, url){
    console.log('UpdateUserCart called')

    fetch(url, {
        method:'POST',
        headers:{
            'Content-Type':'application/json',
            'X-CSRFToken':csrftoken,
        },
        body:JSON.stringify({'inventoryId':inventoryId, 'action':action})
    })
    .then(res => res.json())
    .then((data) =>{
        console.log('data:', data)
        document.getElementById('addCart').innerHTML = `${data.qty}`
    })
    .catch((error) => {
        console.error('❌ Cart update failed:', error);
        alert('Failed to update cart. Please try again.');
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
        headers:{
            'Content-Type':'application/json',
            'X-CSRFToken':csrftoken,
        },
        body:JSON.stringify(data)
    })
    .then(res => res.json())
    .then((data) =>{
        console.log('Success:', data);
        document.getElementById('sub_total').innerHTML = `${data.sub_total.toFixed(1)}`
        document.getElementById('final_total').innerHTML = `<b>Total:</b><div><i class="fa-solid fa-naira-sign"></i>${data.final_total.toFixed(1)}</div>`
        document.getElementById('sum_quantity').innerHTML = `<b>Item:</b><div>${data.total_quantity}</div>`
        document.getElementById('addCart').innerHTML = `${data.total_quantity}`
        location.reload()
    })
    .catch((error) => {
        console.error('❌ Quantity update failed:', error);
        alert('Failed to update quantity. Please try again.');
    });
}
