# Offline-First System - Quick Start (5 Steps in 15 Minutes)

## What You're Getting
A complete **offline-first sales system** that lets your store continue operations during internet outages. Sales are automatically synced when connection is restored.

---

## Step 1: Update Database (5 min)

**File:** `ims/models.py`

Find the `Sale` model class and add these 3 fields:

```python
class Sale(models.Model):
    # ... existing fields ...
    
    # Offline sync tracking
    sync_from_offline = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this sale was synced from offline mode"
    )
    original_temp_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Original temp ID from offline client"
    )
    sync_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this sale was synced from offline"
    )
    
    # ... rest of model ...
```

Then run:
```bash
python manage.py makemigrations ims
python manage.py migrate ims
```

✅ **Done!** Now proceed to Step 2.

---

## Step 2: Update Base Template (3 min)

**File:** `templates/base.html`

Add this code **before the closing `</body>` tag:**

```html
<!-- Offline-First Support -->
<script>
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/assets/js/service-worker.js')
            .then(() => console.log('✅ Service Worker registered'))
            .catch(() => console.warn('Service Worker registration failed'));
    }
</script>

<!-- Offline Manager -->
<script src="{% static 'assets/js/offline-manager.js' %}"></script>

<!-- Offline Indicator -->
{% include 'partials/offline-indicator.html' %}
```

✅ **Done!** Now proceed to Step 3.

---

## Step 3: Update Store Template (3 min)

**File:** `templates/ims/store.html` (or wherever you have the store/checkout page)

Add this code **inside a `<script>` block:**

```javascript
document.addEventListener('DOMContentLoaded', async () => {
    // Cache products and inventory for offline use
    try {
        const response = await fetch('/ims/api/get-offline-data/');
        const data = await response.json();
        
        if (data.success) {
            await offlineManager.cacheProductData(data.products, data.inventory);
            console.log('✅ Offline data cached');
        }
    } catch (error) {
        console.warn('Could not cache offline data:', error);
    }
});
```

✅ **Done!** Now proceed to Step 4.

---

## Step 4: Restart Server (2 min)

```bash
docker-compose restart web
```

Wait for it to restart (you'll see "✔ Container quicksales Started")

✅ **Done!** Now proceed to Step 5.

---

## Step 5: Test It (2 min)

1. **Open browser:** http://localhost:8000/

2. **Open Developer Tools:** Press `F12`

3. **Go to Network tab → Check "Offline"** (simulates internet loss)

4. **Open store page** → Products should still load from cache

5. **Make a test sale** → Should complete successfully

6. **Check top-right** → Should see **"🔴 Offline Mode | 1 sales queued"**

7. **Uncheck "Offline"** in DevTools (internet restored)

8. **Wait 30 seconds** → Indicator should change to **"🟢 Online"**

9. **Check database** → New Sale record should be created

✅ **Success!** Offline mode is now active!

---

## How to Use

### When Internet is Down ✅
- Customers can still make purchases
- Sales are saved locally
- Red "Offline Mode" indicator shows
- Shows how many sales are queued

### When Internet Comes Back ✅
- Automatic sync happens
- Orange "Syncing..." indicator shows briefly
- Green "Online" indicator returns
- All queued sales are processed

### If There's a Conflict ⚠️
- If inventory is insufficient after sync, system notifies user
- User can adjust quantity and retry
- Server is always the source of truth

---

## Testing Scenarios

### Test 1: Basic Offline
```
1. Open DevTools → Network → Check "Offline"
2. Make a sale
3. See "Offline Mode" indicator
4. Uncheck "Offline"
5. Wait 30 seconds
6. Sale should sync automatically
```

### Test 2: Multiple Offline Sales
```
1. Check "Offline"
2. Make 5 sales
3. Indicator shows "5 sales queued"
4. Uncheck "Offline"
5. All 5 should sync
```

### Test 3: Check Indicator States
```
Green "Online" = Connected to server
Red "Offline Mode" = No internet, sales queued
Orange "Syncing..." = Currently syncing
```

---

## Troubleshooting

### Problem: Offline indicator not showing
**Solution:** 
1. Hard refresh page (Ctrl+Shift+R)
2. Check browser console for errors
3. Verify offline-indicator.html is included

### Problem: Service Worker not registering
**Solution:**
1. Check `/static/assets/js/service-worker.js` file exists
2. Look in DevTools → Application → Service Workers
3. Check browser console for errors

### Problem: Data not syncing when online
**Solution:**
1. Verify internet connection
2. Check API endpoint: `/ims/api/sync-sale/`
3. Look for CSRF token error in console

---

## Files Automatically Created

You DON'T need to create these - they're already done:

✅ `/ImsV3/static/assets/js/offline-manager.js` (500 lines)
✅ `/ImsV3/static/assets/js/service-worker.js` (250 lines)
✅ `/ims/api/offline_sync.py` (200 lines)
✅ `/templates/partials/offline-indicator.html` (100 lines)
✅ `/ims/urls.py` (modified with 3 new API routes)

---

## Documentation

Read these files for more info:

1. **OFFLINE_FINAL_CHECKLIST.md** - Complete step-by-step guide
2. **OFFLINE_MODE_GUIDE.md** - Full documentation
3. **OFFLINE_QUICK_SETUP.sh** - Commands reference

---

## Success Indicators ✅

After following these 5 steps, you should see:

- ✅ Green "Online" indicator in top-right
- ✅ Offline simulation works (toggle in DevTools)
- ✅ Sales can be made offline
- ✅ Automatic sync when online
- ✅ No errors in browser console
- ✅ Sales appear in database after sync

---

## Next: Deployment

When ready for production:

1. Review `OFFLINE_MODE_GUIDE.md`
2. Test thoroughly on staging
3. Roll out to 1-2 branches first
4. Monitor for any issues
5. Gradually expand to all branches

---

## Support

For detailed help:
- Check `OFFLINE_MODE_GUIDE.md`
- Review browser DevTools (Console, Network, Application tabs)
- Check server logs for sync errors
- Reference `OFFLINE_FINAL_CHECKLIST.md` troubleshooting section

---

**You're done! Your system is now offline-ready.** 🎉

**Time spent:** ~15 minutes
**Result:** Continuous sales during internet outages ✅
**Revenue protection:** 100% 💰
