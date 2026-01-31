# Coupon System - Quick Reference Guide

## For Developers

### API Endpoints

#### 1. Validate Coupon & Get Discount Preview
**Endpoint:** `POST /subscriptions/api/validate-coupon/`

**Request:**
```javascript
const response = await fetch('/subscriptions/api/validate-coupon/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCookie('csrftoken')
  },
  body: JSON.stringify({
    coupon_code: 'SAVE10',
    plan_id: 'plan-uuid-here'
  })
});

const data = await response.json();
```

**Success Response (200):**
```json
{
  "success": true,
  "message": "Coupon applied successfully",
  "original_amount": 99.99,
  "discount": 9.99,
  "final_amount": 90.00,
  "coupon_type": "percent",
  "coupon_id": "coupon-uuid"
}
```

**Error Response (400):**
```json
{
  "success": false,
  "message": "Invalid coupon code",
  "original_amount": 99.99
}
```

**Error Messages:**
- `"Invalid coupon code"` - Coupon doesn't exist
- `"Coupon is no longer valid"` - Expired or not yet active
- `"Coupon has reached maximum uses"` - All redemptions exhausted
- `"You have already used this coupon"` - Organization already redeemed

#### 2. Apply Coupon to Existing Subscription
**Endpoint:** `POST /subscriptions/api/apply-coupon/<subscription_id>/`

**Request:**
```javascript
const response = await fetch(`/subscriptions/api/apply-coupon/${subscriptionId}/`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCookie('csrftoken')
  },
  body: JSON.stringify({
    coupon_code: 'SAVE10'
  })
});

const data = await response.json();
```

**Success Response (200):**
```json
{
  "success": true,
  "message": "Coupon applied to subscription",
  "coupon_code": "SAVE10"
}
```

**Error Response (400):**
```json
{
  "success": false,
  "message": "You have already used this coupon"
}
```

### Payment Flow with Coupon

```javascript
// User clicks "Subscribe" after entering coupon code

// Step 1: Validate coupon
const couponCode = document.getElementById('coupon-input').value;
const planId = document.getElementById('plan-id').value;

const validation = await fetch('/subscriptions/api/validate-coupon/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCookie('csrftoken')
  },
  body: JSON.stringify({
    coupon_code: couponCode,
    plan_id: planId
  })
});

if (validation.ok) {
  const discountData = await validation.json();
  
  // Show discount preview
  document.getElementById('discount-amount').innerText = 
    `$${discountData.discount.toFixed(2)}`;
  document.getElementById('final-amount').innerText = 
    `$${discountData.final_amount.toFixed(2)}`;
  
  // Step 2: Initialize payment with coupon
  const paymentInit = await fetch(`/subscriptions/plan/init/${planId}/?coupon_code=${couponCode}`);
  
  if (paymentInit.ok) {
    const paymentData = await paymentInit.json();
    // Redirect to Paystack payment URL
    window.location.href = paymentData.authorization_url;
  }
} else {
  const error = await validation.json();
  showError(error.message);
}
```

---

## For Admin Users

### Creating a Coupon

1. Navigate to **Admin Panel** → **Subscriptions** → **Coupons**
2. Click **+ Add Coupon**
3. Fill in the form:
   
   **Basic Info:**
   - **Code**: Unique identifier (auto-uppercased, e.g., `SAVE10`)
   - **Type**: Select from:
     - `Percent Off` - % discount (e.g., 10 = 10% off)
     - `Fixed Amount` - Currency discount (e.g., 10 = $10 off)
     - `Free Month` - Full month free
   - **Active**: Check to enable immediately

   **Discount Value:**
   - **Value**: Discount amount (0-100 for percent, or fixed amount)
   - **Duration Days**: How long the benefit lasts (default: 30)

   **Usage Limits:**
   - **Max Uses**: Maximum redemptions allowed (default: 100)
   - Uses (read-only): Current count

   **Validity Period:**
   - **Start Date**: When coupon becomes valid
   - **End Date**: When coupon expires (optional)

4. Click **Save**

### Example Configurations

#### Example 1: 10% Off
```
Code: SUMMER20
Type: Percent Off
Value: 10
Max Uses: 50
Start Date: 2024-06-01
End Date: 2024-08-31
Active: ✓
```

#### Example 2: $10 Off
```
Code: WELCOME10
Type: Fixed Amount
Value: 10
Max Uses: 100
Start Date: 2024-01-01
End Date: (empty - no expiration)
Active: ✓
```

#### Example 3: Free First Month
```
Code: FREETRIAL
Type: Free Month
Value: 0 (not used for free month)
Duration Days: 30
Max Uses: 1000
Start Date: 2024-01-01
Active: ✓
```

### Viewing Coupon Redemptions

1. Navigate to **Admin Panel** → **Subscriptions** → **Coupon Redemptions**
2. View all times coupons were used:
   - **Coupon**: Which coupon was redeemed
   - **Organization**: Which org used it
   - **Subscription**: Associated subscription
   - **Used At**: When it was redeemed

### Monitoring Coupon Usage

In the **Coupons** list:
- Check **Uses** column to see current redemption count
- Compare with **Max Uses** to track remaining capacity
- Disable coupon by unchecking **Active** if needed

---

## Database Queries

### Get All Active Coupons
```python
from subscriptions.models import Coupon

active = Coupon.objects.filter(
    is_active=True,
    start_date__lte=timezone.now()
)
# Filter further by type if needed
```

### Get Coupon Redemptions for Organization
```python
from subscriptions.models import CouponRedemption
from account.models import Organization

org = Organization.objects.get(id=org_id)
redemptions = CouponRedemption.objects.filter(organization=org)

# Count unique coupons used by org
used_coupon_codes = redemptions.values_list('coupon__code', flat=True).distinct()
```

### Check if Organization Used Specific Coupon
```python
has_used = CouponRedemption.objects.filter(
    coupon__code='SAVE10',
    organization=org
).exists()
```

### Find Expired Coupons
```python
from django.utils import timezone

expired = Coupon.objects.filter(
    end_date__lt=timezone.now(),
    is_active=True
)

# Deactivate them
expired.update(is_active=False)
```

---

## Troubleshooting

### Coupon Not Showing in Validation
- ✓ Check coupon code spelling (codes are case-insensitive)
- ✓ Verify start_date has passed (check server time)
- ✓ Verify end_date hasn't passed (if set)
- ✓ Confirm is_active checkbox is checked
- ✓ Check max_uses hasn't been reached

### Discount Amount Looks Wrong
- For **Percent**: Check value is 0-100 (10 = 10%)
- For **Fixed**: Check value matches currency
- For **Free Month**: Final amount should be $0

### Organization Can't Reuse Coupon
- This is intentional - designed to prevent abuse
- Each organization can use each coupon only once
- Check **Coupon Redemptions** to see org's history

### Payment Shows Wrong Amount
- Ensure validation happened before payment init
- Check Payment record has coupon FK populated
- Verify init_payment received coupon_code parameter

---

## Performance Considerations

- Coupon codes are indexed (fast lookups)
- Redemptions indexed by organization + coupon
- Use `.select_related()` when querying redemptions with coupons:
  ```python
  redemptions = CouponRedemption.objects.select_related(
      'coupon', 'organization', 'subscription'
  )
  ```

---

## Security Notes

1. **Case Insensitivity**: Codes are automatically uppercased to prevent case-based duplicates
2. **Organization Isolation**: Users can't see other orgs' redemption history
3. **Rate Limiting**: Consider adding rate limiting to validate_coupon_api endpoint
4. **Duplicate Prevention**: CouponRedemption prevents misuse via database constraint
5. **Admin Only**: Coupon creation/editing restricted to admin users

---

## API Response Status Codes

| Code | Meaning |
|------|---------|
| 200 | Coupon validated successfully |
| 400 | Invalid coupon code or business logic error |
| 405 | Wrong HTTP method (must be POST) |
| 500 | Server error (check logs) |

---

## Sample Usage in Django Template

```html
<!-- Coupon Input -->
<div class="form-group">
  <label for="coupon">Coupon Code (Optional)</label>
  <input type="text" id="coupon" placeholder="Enter coupon code" class="form-control">
  <button type="button" onclick="validateCoupon()" class="btn btn-secondary mt-2">
    Apply Coupon
  </button>
</div>

<!-- Discount Display -->
<div id="discount-info" style="display:none;">
  <p>Discount: <strong id="discount-amount">$0.00</strong></p>
  <p>Final Amount: <strong id="final-amount">$99.99</strong></p>
</div>

<script>
async function validateCoupon() {
  const couponCode = document.getElementById('coupon').value.trim();
  const planId = '{{ plan.id }}';
  
  if (!couponCode) {
    alert('Please enter a coupon code');
    return;
  }
  
  try {
    const response = await fetch('/subscriptions/api/validate-coupon/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': '{{ csrf_token }}'
      },
      body: JSON.stringify({
        coupon_code: couponCode,
        plan_id: planId
      })
    });
    
    const data = await response.json();
    
    if (data.success) {
      document.getElementById('discount-amount').textContent = 
        `$${data.discount.toFixed(2)}`;
      document.getElementById('final-amount').textContent = 
        `$${data.final_amount.toFixed(2)}`;
      document.getElementById('discount-info').style.display = 'block';
      alert('Coupon applied! Discount: $' + data.discount.toFixed(2));
    } else {
      alert('Error: ' + data.message);
    }
  } catch (error) {
    alert('Error validating coupon: ' + error);
  }
}
</script>
```

---

## Changelog

### Version 1.0.0 (Initial Release)
- Coupon model with percent, fixed, and free_month types
- CouponRedemption tracking per organization
- Admin interface for coupon management
- API endpoints for validation and application
- Payment integration with coupon field
- Form validation and error handling
