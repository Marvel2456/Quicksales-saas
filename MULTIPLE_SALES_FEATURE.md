# Multiple Concurrent Sales Feature

## Overview
This feature allows POS users to handle multiple customers simultaneously by creating and managing multiple sale sessions. Each sale can be completed independently when payment is made, and sessions can be cancelled if a customer doesn't proceed with purchase.

## Use Case
**Scenario**: You have two customers (Customer A and Customer B) at the counter:
1. Start scanning items for Customer A
2. Customer B arrives and wants to make a quick purchase
3. Create a new sale session for Customer B
4. Complete Customer B's sale
5. Switch back to Customer A's session
6. Complete Customer A's sale

## Features Implemented

### 1. Session-Based Sale Tracking
- Each branch tracks its active sale in the user's session
- Session key format: `active_sale_{branch_id}`
- Active sale persists across page refreshes within the same session
- Completed sales automatically clear from session

### 2. New Endpoints

#### Create New Sale
- **URL**: `/sale/<branch_id>/new/`
- **Method**: GET
- **Action**: Creates a new sale session and sets it as active
- **Response**: Redirects to cart with success message showing sale ID

#### Switch Sale
- **URL**: `/sale/<branch_id>/switch/<sale_id>/`
- **Method**: GET
- **Action**: Switches to a different open sale session
- **Response**: Redirects to cart with confirmation message

#### Cancel Sale
- **URL**: `/sale/<branch_id>/cancel/<sale_id>/`
- **Method**: GET
- **Action**: Deletes sale and all items, clears from session if active
- **Confirmation**: Requires user confirmation
- **Response**: Redirects to cart with success message

### 3. Updated Views

#### cart()
- Retrieves active sale from session
- Lists all open (uncompleted) sales for the staff
- Creates new sale if no active sale exists
- Displays multi-sale management UI

#### checkout()
- Uses session-based active sale instead of `get_or_create`
- Prevents conflicts with multiple sale sessions

#### sale_complete()
- Already used session-based tracking
- Now clears session on completion

#### updateCart() & updateQuantity()
- Updated to work with session-based active sale
- Create new sale if none exists

### 4. UI Changes (cart.html)

The cart page now shows:

**Multi-Sale Management Panel** (appears when there are multiple open sales):
- **Open Sales Buttons**: Shows all open sale sessions as buttons
  - Active sale highlighted in primary color
  - Each button shows item count badge
  - Click to switch between sales
  
- **New Sale Button**: Creates a fresh sale session
  
- **Cancel Current Button**: Removes current sale (with confirmation)

**Visual Indicators**:
- Current active sale is highlighted
- Item count badges show how many items in each sale
- Sales numbered sequentially (Sale #1, Sale #2, etc.)

## Technical Details

### Session Management
```python
# Set active sale
request.session[f'active_sale_{branch.id}'] = str(sale.id)

# Get active sale
active_sale_id = request.session.get(f'active_sale_{branch.id}')

# Clear active sale
request.session.pop(f'active_sale_{branch.id}', None)
```

### Sale Retrieval Pattern
```python
# Get active sale from session
active_sale_id = request.session.get(f'active_sale_{branch.id}')
if active_sale_id:
    try:
        sale = Sale.objects.get(
            id=active_sale_id, 
            staff=staff, 
            branch=branch, 
            completed=False
        )
    except Sale.DoesNotExist:
        # Create new if active sale not found
        sale = Sale.objects.create(staff=staff, branch=branch, organization=organization)
        request.session[f'active_sale_{branch.id}'] = str(sale.id)
else:
    # Create new if no active sale
    sale = Sale.objects.create(staff=staff, branch=branch, organization=organization)
    request.session[f'active_sale_{branch.id}'] = str(sale.id)
```

## Files Modified

1. **ims/view/sale_views.py**
   - Added `create_new_sale()`, `switch_sale()`, `cancel_sale()`
   - Updated `cart()`, `checkout()`, `updateCart()`, `updateQuantity()`
   - Enhanced `sale_complete()` to clear session

2. **ims/urls.py**
   - Added URL patterns for new endpoints
   - Updated imports

3. **templates/ims/cart.html**
   - Added multi-sale management UI
   - Sale switcher buttons
   - New sale and cancel buttons

## Workflow Example

### Scenario: Two Customers

1. **Customer A arrives**
   - System creates or loads active sale
   - Scan Customer A's items
   
2. **Customer B arrives (urgent)**
   - Click "New Sale" button
   - System creates Sale #2 and switches to it
   - Scan Customer B's items
   - Click "Checkout" → Complete payment
   - Sale #2 completed and removed from session
   
3. **Return to Customer A**
   - System automatically shows Sale #1 (only open sale)
   - OR click "Sale #1" button to switch
   - Continue scanning items
   - Click "Checkout" → Complete payment
   - Sale #1 completed

4. **Customer A decides not to buy**
   - Click "Cancel Current" button
   - Confirm cancellation
   - Sale and all items deleted
   - No record in completed sales

## Benefits

1. **No Lost Sales**: Handle multiple customers without losing data
2. **Flexibility**: Switch between sales as needed
3. **Clean Cancellation**: Remove unwanted sales completely
4. **User-Friendly**: Visual indicators show which sale is active
5. **Session Isolation**: Each staff member has independent sale sessions
6. **Branch Isolation**: Sales tracked per branch

## Security & Validation

- All endpoints require `@login_required` and `@role_required(['owner', 'sales'])`
- Sales validated to belong to current staff, branch, and organization
- Only uncompleted sales can be switched to or cancelled
- Session-based tracking prevents cross-contamination

## Future Enhancements

Potential improvements:
- Add customer name/identifier to sales
- Show timestamp for each open sale
- Auto-timeout for abandoned sales
- Sale notes/comments
- Print queue for completed sales
