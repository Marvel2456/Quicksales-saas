# Offline-First Sales System - Implementation Guide

## Quick Start

### 1. **Register Service Worker**
Add this to your base template (usually `templates/base.html`):

```html
<!-- At the end of body, before closing </body> tag -->
<script>
    // Register Service Worker for offline support
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/assets/js/service-worker.js')
            .then((registration) => {
                console.log('✅ Service Worker registered:', registration);
            })
            .catch((error) => {
                console.warn('Service Worker registration failed:', error);
            });
    }
</script>

<!-- Include Offline Manager -->
<script src="{% static 'assets/js/offline-manager.js' %}"></script>

<!-- Include Offline Indicator -->
{% include 'partials/offline-indicator.html' %}
```

### 2. **Initialize on Store Page**
Add to your store template:

```javascript
<script>
    document.addEventListener('DOMContentLoaded', async () => {
        // Cache products and inventory when page loads
        const response = await fetch('/ims/api/get-offline-data/');
        const data = await response.json();
        
        if (data.success) {
            await offlineManager.cacheProductData(data.products, data.inventory);
            console.log('✅ Offline data cached');
        }
    });
</script>
```

## How It Works

### Online Mode (Normal Operation)
```
User makes sale
    ↓
Standard Django flow
    ↓
Data saved to server
    ↓
Data synced to client cache
```

### Offline Mode (No Internet)
```
Internet disconnected
    ↓
User can still make sales
    ↓
Sales stored in IndexedDB
    ↓
Inventory decremented locally
    ↓
Offline indicator shows "Offline Mode | X sales queued"
    ↓
Internet restored
    ↓
Automatic sync with server
    ↓
Conflicts resolved
    ↓
UI shows "Synced"
```

## Key Features

### 1. **Automatic Caching**
- Products and inventory cached when page loads
- Updates every time user views store
- Cache survives browser restart

### 2. **Pending Sales Queue**
- Sales made offline stored locally
- Retry mechanism with exponential backoff
- Conflict detection for inventory issues

### 3. **Smart Syncing**
- Automatic sync when connection restored
- Manual "Sync Now" button available
- Progress indicators show sync status

### 4. **Conflict Resolution**
```
Conflict Scenario: Inventory mismatch during sync
    ↓
Server has less stock than offline sale requested
    ↓
Response: 409 Conflict error
    ↓
UI shows: "Insufficient inventory. Please adjust quantity."
    ↓
User can manually adjust and retry
```

## API Endpoints

### GET /ims/api/get-offline-data/
Returns products and inventory for offline caching.

**Response:**
```json
{
    "success": true,
    "products": [
        {
            "id": "uuid",
            "product_name": "Pen",
            "product_code": "PEN001",
            "category__category_name": "Stationery",
            "brand": "BIC"
        }
    ],
    "inventory": [
        {
            "id": "uuid",
            "product_id": "uuid",
            "quantity": 50,
            "sale_price": 100,
            "cost_price": 50,
            "status": "Available"
        }
    ],
    "timestamp": "2026-01-23T10:30:00Z"
}
```

### POST /ims/api/sync-sale/
Syncs a pending sale from offline mode.

**Request:**
```json
{
    "tempId": 1234567890,
    "items": [
        {
            "product_id": "uuid",
            "quantity": 5,
            "unit_price": 100,
            "cost_price": 50
        }
    ],
    "total_amount": 500,
    "payment_method": "cash",
    "payment_status": "paid"
}
```

**Success Response (200):**
```json
{
    "success": true,
    "message": "Sale synced successfully",
    "sale_id": "uuid",
    "total_amount": 500,
    "items_count": 1
}
```

**Conflict Response (409):**
```json
{
    "error": "Insufficient inventory",
    "details": [
        {
            "product_id": "uuid",
            "requested": 10,
            "available": 5,
            "status": "insufficient"
        }
    ]
}
```

### GET /ims/api/sync-status/
Get current sync status.

**Response:**
```json
{
    "is_online": true,
    "last_sync": "2026-01-23T10:30:00Z",
    "pending_count": 0
}
```

## Database Schema Updates

Add these fields to the `Sale` model to track offline syncs:

```python
class Sale(models.Model):
    # ... existing fields ...
    
    # Offline sync tracking
    sync_from_offline = models.BooleanField(
        default=False,
        help_text="Whether this sale was synced from offline mode"
    )
    original_temp_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Original temp ID from offline client"
    )
    sync_timestamp = models.DateTimeField(
        auto_now_add=True,
        help_text="When this sale was synced from offline"
    )
```

Run migration:
```bash
python manage.py makemigrations
python manage.py migrate
```

## Testing Offline Mode

### Manual Testing
1. Open developer tools (F12)
2. Go to Network tab
3. Check "Offline" checkbox (simulates offline mode)
4. Try making a sale
5. Check offline indicator - should show "Offline Mode | 1 sales queued"
6. Uncheck "Offline" 
7. Wait 30 seconds or click manual sync
8. Check console for sync messages

### Testing in DevTools
```javascript
// In browser console
offlineManager.getStatus()
// Returns: {isOnline: true, pendingSalesCount: 0, syncInProgress: false}

// Simulate offline
offlineManager.onOffline()

// Simulate online
offlineManager.onOnline()

// Get pending sales
const pending = await offlineManager.getPendingSales()
console.log(pending)

// Clear all offline data (dangerous!)
await offlineManager.clearAllData()
```

## Performance Considerations

| Metric | Value |
|--------|-------|
| Cache Size | ~5-10 MB for typical inventory |
| Sync Interval | 30 seconds (configurable) |
| Retry Attempts | 3 attempts before manual intervention |
| Cache Duration | 24 hours (auto-refreshed on page load) |
| IndexedDB Quota | 50 MB (per origin, browser dependent) |

## Troubleshooting

### Service Worker Not Registering
```javascript
// Check in console
navigator.serviceWorker.controller // should exist
navigator.serviceWorker.ready // wait for this promise
```

### Offline Manager Not Initializing
```javascript
// Check browser support
console.log('IndexedDB:', !!window.indexedDB)
console.log('ServiceWorker:', 'serviceWorker' in navigator)
console.log('Fetch API:', 'fetch' in window)
```

### Pending Sales Not Syncing
1. Check network connectivity
2. Verify CSRF token is set: `document.querySelector('[name=csrfmiddlewaretoken]')`
3. Check browser console for errors
4. View IndexedDB: DevTools → Application → IndexedDB → quicksales_offline

### Database Quota Exceeded
```javascript
// Clear IndexedDB and start fresh
await offlineManager.clearAllData()
// Reload page
location.reload()
```

## Migration Strategy

### Phase 1: Deployment (No Changes to UX)
- Deploy service worker, offline manager, sync API
- Offline mode silently available
- Monitor console logs

### Phase 2: Opt-In (Users can enable)
- Add toggle in settings
- Show offline indicator only if enabled
- Gather feedback

### Phase 3: Default On (Full rollout)
- Enable for all users
- Offline indicator always visible
- Full feature availability

## Security Considerations

⚠️ **Important**: 

1. **IndexedDB is not encrypted** - Don't store sensitive data offline
2. **Sync validation** - Server validates all synced data before committing
3. **CSRF Protection** - Offline sync includes CSRF token
4. **Rate Limiting** - Implement rate limits on sync endpoint
5. **User Isolation** - Each user syncs only their own sales

## Rollback Plan

If issues occur in production:

```bash
# 1. Disable service worker registration
# (Comment out the registration code in base.html)

# 2. Disable offline endpoints (temporarily)
# Set in settings.py:
OFFLINE_SYNC_ENABLED = False

# 3. Clear browser cache
# Users: Ctrl+Shift+Delete → Clear browsing data

# 4. Recovery
# Manually review pending_sales in database
# Either sync manually or discard with caution
```

## Next Steps

1. ✅ Update base.html with service worker registration
2. ✅ Add offline indicator to store pages
3. ✅ Update Sale model with offline tracking fields
4. ✅ Run migrations
5. ✅ Test in offline mode
6. ✅ Monitor sync errors in production
7. ✅ Gather user feedback
8. ✅ Optimize based on usage patterns

## Monitoring & Analytics

Add to offline-manager.js to track metrics:

```javascript
// Track sync success rate
track('offline.sync.attempted', {sync_count: pendingSales.length})
track('offline.sync.success', {synced_count: successCount})
track('offline.sync.failed', {failed_count: failureCount})

// Track offline usage
track('offline.session.started', {duration: onlineDuration})
track('offline.sales.made', {count: offlineSalesCount})
```

## Support & Documentation

- **User Guide**: How to use offline mode
- **Admin Guide**: Monitoring and troubleshooting
- **Developer Guide**: This document
- **FAQ**: Common questions and answers

---

**Version:** 1.0
**Last Updated:** 2026-01-23
**Status:** Ready for Beta Testing
