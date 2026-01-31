# Testing Guide: Multiple Concurrent Sales Feature

## Prerequisites
1. Django server running: `python manage.py runserver`
2. Valid user account with 'owner' or 'sales' role
3. At least one branch with inventory items

## Test Scenarios

### Scenario 1: Basic Multiple Sales Flow

**Objective**: Verify creating and switching between multiple sales

**Steps**:
1. Login as a sales staff or owner
2. Navigate to Store → Select a branch → View cart
3. Add items to cart (this creates Sale #1 automatically)
4. **Expected**: Cart shows items, no multi-sale panel appears (only 1 sale)
5. Click "New Sale" button
6. **Expected**: 
   - Success message: "New sale session created (ID: xxxxxxxx)"
   - Cart is now empty (switched to Sale #2)
   - Multi-sale panel appears showing both sales
7. Add different items to Sale #2
8. Click on "Sale #1" button in multi-sale panel
9. **Expected**:
   - Success message: "Switched to sale (ID: xxxxxxxx)"
   - Cart shows Sale #1 items
   - Sale #1 button is highlighted (primary color)
10. Click on "Sale #2" button
11. **Expected**: Cart shows Sale #2 items

**Validation**:
- ✓ Each sale maintains its own items
- ✓ Switching doesn't lose data
- ✓ Active sale is visually indicated

---

### Scenario 2: Complete One Sale While Another is Open

**Objective**: Verify independent completion of sales

**Steps**:
1. Continue from Scenario 1 with 2 open sales
2. Switch to Sale #2
3. Click "Checkout"
4. Enter payment details
5. Click "Make Payment"
6. **Expected**:
   - Success message: "sale completed"
   - Redirected to receipt page
7. Navigate back to cart
8. **Expected**:
   - Only Sale #1 button shows in multi-sale panel
   - Sale #2 is removed (completed)
9. Complete Sale #1
10. **Expected**: 
    - Multi-sale panel disappears (no open sales)
    - Cart is empty

**Validation**:
- ✓ Completed sales are removed from session
- ✓ Other sales remain unaffected
- ✓ Can complete sales in any order

---

### Scenario 3: Cancel a Sale

**Objective**: Verify sale cancellation works correctly

**Steps**:
1. Create 2 sales with items
2. Switch to Sale #1
3. Click "Cancel Current" button
4. **Expected**: Confirmation dialog appears
5. Click "OK" to confirm
6. **Expected**:
   - Success message: "Sale cancelled successfully"
   - Sale #1 is removed from panel
   - Only Sale #2 remains
7. Navigate to Sales History (if accessible)
8. **Expected**: Cancelled sale does NOT appear in history

**Validation**:
- ✓ Sale and all items are deleted
- ✓ No record in completed sales
- ✓ Session is updated correctly

---

### Scenario 4: Multiple Staff Members

**Objective**: Verify sale isolation between staff

**Steps**:
1. Login as Staff A
2. Create Sale #1 with items
3. Logout
4. Login as Staff B (different user)
5. Navigate to same branch → cart
6. **Expected**: 
   - Cart is empty
   - No multi-sale panel (no open sales for Staff B)
7. Create Sale #1 for Staff B
8. Logout
9. Login as Staff A again
10. Navigate to cart
11. **Expected**: Staff A's Sale #1 is still there with items intact

**Validation**:
- ✓ Sales are isolated per staff member
- ✓ No cross-contamination between users

---

### Scenario 5: Multiple Branches

**Objective**: Verify sale isolation between branches

**Steps**:
1. Login as owner with access to multiple branches
2. Select Branch A → Create Sale #1 with items
3. Navigate to Branch B → View cart
4. **Expected**: Cart is empty (separate session)
5. Create Sale #1 in Branch B with different items
6. Switch back to Branch A
7. **Expected**: Branch A's Sale #1 is still there

**Validation**:
- ✓ Each branch has independent sale sessions
- ✓ Session keys are branch-specific

---

### Scenario 6: Session Persistence

**Objective**: Verify sales persist across page refreshes

**Steps**:
1. Create 2 sales with items
2. Refresh the cart page (F5 or Cmd+R)
3. **Expected**: 
   - Both sales still show in panel
   - Active sale is still active
   - Items are intact
4. Switch to other sale
5. Refresh page
6. **Expected**: Switched sale is now active

**Validation**:
- ✓ Session data persists
- ✓ Active sale tracking maintained

---

### Scenario 7: Edge Cases

#### 7a: Cancel Last Sale
**Steps**:
1. Create 1 sale with items
2. Click "Cancel Current"
3. Confirm
4. **Expected**:
   - Cart is empty
   - No multi-sale panel
   - Can continue shopping (creates new sale)

#### 7b: Cancel Active Sale with Multiple Open
**Steps**:
1. Create 3 sales
2. Switch to Sale #2 (middle one)
3. Cancel Sale #2
4. **Expected**:
   - Removed from panel
   - Automatically shows Sale #1 or Sale #3 (implementation dependent)

#### 7c: Empty Sale
**Steps**:
1. Create new sale
2. Don't add any items
3. Click checkout
4. **Expected**: Should handle gracefully (may show validation)

#### 7d: Concurrent Updates
**Steps**:
1. Open cart in two browser tabs
2. Create sale in Tab 1
3. Refresh Tab 2
4. Add items in both tabs
5. **Expected**: Last write wins (Django session behavior)

---

## API Endpoint Testing

### Test Create New Sale Endpoint

**Request**:
```
GET /sale/<branch_id>/new/
```

**Expected Response**:
- 302 Redirect to cart
- Session updated with new sale ID
- Success message in messages framework

**Test with CURL**:
```bash
curl -X GET http://localhost:8000/sale/<branch_uuid>/new/ \
  -H "Cookie: sessionid=<your_session_id>" \
  -L
```

---

### Test Switch Sale Endpoint

**Request**:
```
GET /sale/<branch_id>/switch/<sale_id>/
```

**Expected Response**:
- 302 Redirect to cart
- Session updated with specified sale ID
- Success message

**Error Cases**:
- Invalid sale_id → 404 error message
- Sale belongs to different staff → 404 error message
- Sale already completed → 404 error message

---

### Test Cancel Sale Endpoint

**Request**:
```
GET /sale/<branch_id>/cancel/<sale_id>/
```

**Expected Response**:
- 302 Redirect to cart
- Sale and items deleted from database
- Session cleared if it was active
- Success message

**Validation**:
```python
# In Django shell
from ims.models import Sale, SalesItem

# Before cancel
sale = Sale.objects.get(id='<sale_id>')
items = sale.salesitem_set.all()
print(f"Items before: {items.count()}")

# After cancel (should raise DoesNotExist)
sale = Sale.objects.get(id='<sale_id>')  # Should fail
```

---

## Database Verification

### Check Sales in Database

**Django Shell Commands**:
```python
from ims.models import Sale, SalesItem
from account.models import CustomUser

# Get all uncompleted sales for a staff
staff = CustomUser.objects.get(email='staff@example.com')
open_sales = Sale.objects.filter(staff=staff, completed=False)
print(f"Open sales: {open_sales.count()}")
for sale in open_sales:
    print(f"Sale {sale.id}: {sale.get_cart_items} items, Total: {sale.get_cart_total}")

# Check sale items
sale = open_sales.first()
items = sale.salesitem_set.all()
for item in items:
    print(f"{item.inventory.product.product_name}: {item.quantity} x {item.inventory.sale_price}")
```

---

## Performance Testing

### Test with Many Sales

**Steps**:
1. Create 10 open sales
2. Add items to each
3. **Monitor**:
   - Page load time for cart
   - Database query count
   - Session size
4. **Expected**:
   - Page loads in < 2 seconds
   - Reasonable query count (use Django Debug Toolbar)

---

## Security Testing

### Test Unauthorized Access

**Test 1**: Access without login
```bash
curl http://localhost:8000/sale/<branch_id>/new/
# Expected: 302 redirect to login
```

**Test 2**: Access other staff's sale
```python
# Login as Staff A
# Get sale ID from Staff B
# Try to switch to Staff B's sale
# Expected: "Sale not found" error
```

**Test 3**: Access other organization's sale
```python
# Login to Org A
# Try to switch to sale from Org B
# Expected: "Sale not found" error
```

---

## UI/UX Testing

### Visual Checks

1. **Multi-sale panel**:
   - ✓ Shows only when 2+ sales or 0 sales
   - ✓ Buttons are properly styled
   - ✓ Active sale is highlighted
   - ✓ Item count badges are visible

2. **Responsive design**:
   - ✓ Test on mobile screen size
   - ✓ Test on tablet
   - ✓ Buttons stack properly on small screens

3. **Messages**:
   - ✓ Success messages appear
   - ✓ Error messages are clear
   - ✓ Messages auto-dismiss or closeable

---

## Regression Testing

Ensure existing functionality still works:

1. **Single Sale Flow**:
   - Add items to cart
   - Checkout
   - Complete payment
   - ✓ Works without multi-sale features

2. **Receipt Printing**:
   - Complete a sale
   - View receipt
   - ✓ Receipt shows correct data

3. **Sales History**:
   - Complete multiple sales
   - View sales history
   - ✓ All completed sales appear
   - ✓ Cancelled sales do NOT appear

4. **Inventory Updates**:
   - Complete sale
   - Check inventory levels
   - ✓ Inventory decrements correctly

---

## Automated Test Script (Optional)

Create a Django test case:

```python
from django.test import TestCase, Client
from django.urls import reverse
from account.models import CustomUser, Organization, Branch
from ims.models import Sale, Category, Product, Inventory

class MultipleSalesTest(TestCase):
    def setUp(self):
        # Create test organization
        self.org = Organization.objects.create(name='Test Org')
        
        # Create test user
        self.user = CustomUser.objects.create_user(
            email='test@example.com',
            password='password123',
            organization=self.org,
            role='sales'
        )
        
        # Create test branch
        self.branch = Branch.objects.create(
            name='Test Branch',
            organization=self.org
        )
        
        # Create test product and inventory
        category = Category.objects.create(name='Test Cat', organization=self.org)
        product = Product.objects.create(
            product_name='Test Product',
            category=category,
            organization=self.org
        )
        self.inventory = Inventory.objects.create(
            product=product,
            branch=self.branch,
            quantity=100,
            sale_price=1000,
            organization=self.org
        )
        
        self.client = Client()
        self.client.login(email='test@example.com', password='password123')
    
    def test_create_new_sale(self):
        """Test creating a new sale session"""
        url = reverse('create_new_sale', kwargs={'pk': self.branch.id})
        response = self.client.get(url)
        
        # Check redirect
        self.assertEqual(response.status_code, 302)
        
        # Check session
        sale_id = self.client.session.get(f'active_sale_{self.branch.id}')
        self.assertIsNotNone(sale_id)
        
        # Check sale exists
        sale = Sale.objects.get(id=sale_id)
        self.assertEqual(sale.staff, self.user)
        self.assertEqual(sale.branch, self.branch)
        self.assertFalse(sale.completed)
    
    def test_switch_sale(self):
        """Test switching between sales"""
        # Create two sales
        sale1 = Sale.objects.create(staff=self.user, branch=self.branch, organization=self.org)
        sale2 = Sale.objects.create(staff=self.user, branch=self.branch, organization=self.org)
        
        # Switch to sale1
        url = reverse('switch_sale', kwargs={'pk': self.branch.id, 'sale_id': sale1.id})
        response = self.client.get(url)
        
        # Check session updated
        active_id = self.client.session.get(f'active_sale_{self.branch.id}')
        self.assertEqual(str(active_id), str(sale1.id))
        
        # Switch to sale2
        url = reverse('switch_sale', kwargs={'pk': self.branch.id, 'sale_id': sale2.id})
        response = self.client.get(url)
        
        active_id = self.client.session.get(f'active_sale_{self.branch.id}')
        self.assertEqual(str(active_id), str(sale2.id))
    
    def test_cancel_sale(self):
        """Test cancelling a sale"""
        # Create sale with items
        sale = Sale.objects.create(staff=self.user, branch=self.branch, organization=self.org)
        from ims.models import SalesItem
        item = SalesItem.objects.create(
            sale=sale,
            branch=self.branch,
            inventory=self.inventory,
            quantity=5
        )
        
        # Cancel sale
        url = reverse('cancel_sale', kwargs={'pk': self.branch.id, 'sale_id': sale.id})
        response = self.client.get(url)
        
        # Check sale deleted
        with self.assertRaises(Sale.DoesNotExist):
            Sale.objects.get(id=sale.id)
        
        # Check items deleted
        items = SalesItem.objects.filter(sale=sale)
        self.assertEqual(items.count(), 0)
```

Run tests:
```bash
python manage.py test ims.tests.MultipleSalesTest
```

---

## Checklist

- [ ] All test scenarios pass
- [ ] No errors in Django check
- [ ] No JavaScript console errors
- [ ] UI looks good on all screen sizes
- [ ] Session data persists correctly
- [ ] Security checks pass
- [ ] Performance is acceptable
- [ ] Existing features not broken
- [ ] Documentation is clear

---

## Troubleshooting

### Issue: "No active sale session" error
**Solution**: Check if session middleware is enabled in settings.py

### Issue: Sales not showing in panel
**Solution**: Verify `completed=False` filter in query

### Issue: Can't switch to sale
**Solution**: Ensure sale belongs to current staff and branch

### Issue: Session not persisting
**Solution**: Check browser cookies are enabled

### Issue: UI not updating after switch
**Solution**: Verify page redirect is working, check for JavaScript errors
