# Offline Mode Testing Guide

## Critical Fixes Applied

### 1. Script Loading Order (MOST CRITICAL)
- **Problem**: `offline-manager.js` was loading AFTER `cart.js`, causing `offlineManager` to be undefined
- **Fix**: Moved `offline-manager.js` to load BEFORE `cart.js` in `base.html`
- **Impact**: Cart functionality will now work when offline

### 2. Offline Detection Improvement
- **Problem**: DevTools offline mode doesn't trigger browser events
- **Fix**: Added 1-second polling of `navigator.onLine` to catch status changes
- **Impact**: Status indicator now updates when you enable offline in DevTools

### 3. Enhanced Error Logging
- **Improvement**: Added detailed console logging at each step
- **Help**: Check browser console to see exactly where the process breaks if issues occur

---

## Step-by-Step Testing

### Test 1: Verify Offline Detection
1. Open your app in Chrome/Firefox
2. Open DevTools: `F12`
3. Go to **Network** tab
4. Click the **Offline** dropdown and select **Offline**
5. **Expected Result**: 
   - Top-right indicator should change to **"🔴 Offline Mode"** in red
   - Console should show: `"🔄 Online status changed via polling: false"`

### Test 2: Add Item to Cart (Offline)
1. With app in offline mode (from Test 1)
2. Go to the **Store** page
3. Click **"Add to Cart"** on any product
4. **Expected Result**:
   - Green toast notification: **"✅ Item added to cart (offline)"`**
   - Cart count increases in top-right
   - Item is saved to IndexedDB (browser storage)

### Test 3: View Offline Cart
1. With items in offline cart, click the **Cart** icon
2. **Expected Result**:
   - Cart page loads and shows items
   - Shows cart summary with total
   - Has **"Checkout"** button

### Test 4: Add Item to Offline Cart
1. On the offline cart page, click **"+""** next to any item
2. **Expected Result**:
   - Quantity increases
   - Subtotal updates

### Test 5: Checkout Offline
1. Click **"Checkout"** button
2. Fill in customer details
3. Click **"Complete Sale"**
4. **Expected Result**:
   - Toast: **"✅ Sale saved locally (offline)"`**
   - Cart clears
   - Order saved to IndexedDB to sync when online

### Test 6: Go Back Online
1. In DevTools → Network → select **"Online"** (default option)
2. **Expected Result**:
   - Status indicator changes to **"🟢 Online"`** in green
   - If there are pending sales, see: **"🔄 Syncing X pending sale(s)..."`**
   - After sync completes: **"✅ Synced X order(s)"`**

### Test 7: Verify Sync Completed
1. Check backend database:
   ```bash
   cd /Users/eseosa/Documents/Quicksales-saas
   python manage.py shell
   >>> from ims.models import Sale
   >>> Sale.objects.filter(customer_name="YourTestName").count()
   ```
2. Should show the orders you placed while offline

---

## Console Debugging

### What to Look For

**Initialization:**
```
📶 Initial online status: true
✅ IndexedDB opened
✅ Offline Manager initialized. Online: true
```

**When Going Offline (DevTools):**
```
🔄 Online status changed via polling: false
🔴 Connection lost - Offline mode enabled
📡 Connection lost - switched to offline mode
```

**When Adding to Cart (Offline):**
```
⚠️ Offline - saving to cart locally
🔄 Waiting for offline manager to be ready...
📊 Attempt 1/100 - Offline Manager Ready: true
✅ Offline manager is ready, saving item to IndexedDB
✅ Item successfully added to offline cart
📊 Updating UI - Online: false Syncing: false Pending: 1
✅ UI Updated - Current class: offline-indicator offline
```

**When Going Online:**
```
🔄 Online status changed via polling: true
🟢 Back online!
🔄 Syncing 1 pending sale(s)...
✅ Syncing complete - 1 success, 0 failures
```

---

## Troubleshooting

### Issue: Offline indicator doesn't change
**Check in console:**
- Look for: `📊 Updating UI - Online: false`
- If not there, polling isn't detecting the change
- Try: Refresh page (Cmd+R) with offline mode already enabled

### Issue: "Unable to add to cart" error
**Check in console:**
- Look for: `🔄 Waiting for offline manager to be ready...`
- Should show: `✅ Offline manager is ready`
- If timeout error: offline-manager.js may not have loaded (check script order in base.html)

### Issue: Items don't show in offline cart
**Check in console:**
- Verify: `✅ Item successfully added to offline cart`
- Check IndexedDB in DevTools → Application → IndexedDB → quicksales_offline
- Should have data in "cart" object store

### Issue: Sync doesn't happen when going online
**Check in console:**
- Look for: `🔄 Syncing X pending sale(s)...`
- If not there, no pending sales were saved
- Verify sales were added by checking pending object store in IndexedDB

---

## Quick Debug Checklist

- [ ] `navigator.onLine` shows correct value in console
- [ ] `offline-manager.js` loads before `cart.js` in DevTools Network tab
- [ ] `offlineManager` object exists in console: `console.log(offlineManager)`
- [ ] IndexedDB exists: DevTools → Application → IndexedDB
- [ ] Service Worker registered: DevTools → Application → Service Workers
- [ ] Polling interval logs appear: Look for `📊 Attempt X/100` logs

---

## Performance Notes

- **Polling interval**: 1 second (balances responsiveness with battery drain)
- **Cart sync retry**: 100ms checks, max 10 seconds
- **Sync check interval**: 30 seconds
- **Toast timeout**: Auto-dismisses after 4 seconds

