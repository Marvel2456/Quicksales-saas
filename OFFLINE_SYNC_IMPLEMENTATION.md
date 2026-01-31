# Offline-First Sales System Implementation

## Overview
This document outlines the implementation of offline-first capabilities for the store/sales module to enable continuous operation during internet outages.

## Architecture

### 1. **Client-Side Storage (IndexedDB)**
- Cache products and inventory data locally
- Store pending sales transactions
- Maintain sync queue

### 2. **Service Worker**
- Intercept network requests
- Serve cached data when offline
- Queue requests during offline mode

### 3. **Sync Mechanism**
- Detect online/offline status
- Queue transactions for later sync
- Implement conflict resolution
- Background Sync API for reliable syncing

### 4. **UI Indicators**
- Show online/offline status
- Display pending transactions count
- Show sync progress

## Database Schema Changes
None required - we'll use IndexedDB on client-side alongside existing Django models.

## Files to Create

1. `static/js/offline-manager.js` - Offline data manager
2. `static/js/service-worker.js` - Service worker
3. `static/js/sync-queue.js` - Sync queue manager
4. `templates/partials/offline-indicator.html` - UI component
5. `ims/api/offline_sync.py` - Sync API endpoints

## Implementation Flow

### When Making a Sale (Offline):
1. User adds items to cart
2. Network check performed
3. If offline:
   - Store cart in IndexedDB
   - Create transaction record with `sync_status='pending'`
   - Show offline indicator
4. When online:
   - Background sync detects online status
   - Syncs pending transactions
   - Updates inventory
   - Resolves conflicts

### When Creating a Sale (Online):
1. Standard flow continues
2. Data synced immediately
3. No queue needed

## Configuration Needed

```javascript
// offline-config.js
const OFFLINE_CONFIG = {
    DB_NAME: 'quicksales_offline',
    STORES: {
        products: 'products',
        inventory: 'inventory',
        sales: 'sales',
        syncQueue: 'syncQueue'
    },
    SYNC_INTERVAL: 30000, // 30 seconds
    CACHE_DURATION: 86400000 // 24 hours
};
```

## Sync Conflict Resolution

When syncing encounters conflicts:
- **Inventory Mismatch**: Use server version as source of truth
- **Duplicate Sales**: Check against sale_id, merge if same
- **Pricing Changes**: Use current server prices
- **Stock Issues**: Queue for manual review if insufficient stock

## Benefits

✅ Continuous sales during internet outages
✅ Automatic sync when connection restored
✅ No data loss
✅ Seamless user experience
✅ Reduced server load during high traffic

## Rollback Plan

If issues occur:
1. Clear IndexedDB: `indexedDB.deleteDatabase('quicksales_offline')`
2. Reset sync queue
3. Fall back to online-only mode
4. Manual recovery of pending sales from browser storage
