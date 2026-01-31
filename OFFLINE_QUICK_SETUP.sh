#!/bin/bash

# Quick Reference - Offline-First Implementation Commands

# ============================================
# SETUP COMMANDS
# ============================================

# 1. Add Service Worker Registration to Base Template
echo "📝 Add this to templates/base.html (before </body>):"
cat << 'EOF'

<script>
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/assets/js/service-worker.js')
            .then(() => console.log('✅ Service Worker registered'))
            .catch(() => console.warn('Service Worker registration failed'));
    }
</script>
<script src="{% static 'assets/js/offline-manager.js' %}"></script>
{% include 'partials/offline-indicator.html' %}
EOF

echo ""
echo "============================================"
echo ""

# 2. Update Sale Model
echo "📝 Add these fields to ims/models.py (Sale class):"
cat << 'EOF'
    sync_from_offline = models.BooleanField(default=False, db_index=True)
    original_temp_id = models.CharField(max_length=100, blank=True, null=True)
    sync_timestamp = models.DateTimeField(null=True, blank=True)
EOF

echo ""
echo "============================================"
echo ""

# 3. Database Migrations
echo "🗄️ Run these migration commands:"
echo "   python manage.py makemigrations ims"
echo "   python manage.py migrate ims"

echo ""
echo "============================================"
echo ""

# 4. Restart Server
echo "🚀 Restart Django server:"
echo "   docker-compose restart web"

echo ""
echo "============================================"
echo "TESTING COMMANDS"
echo "============================================"
echo ""

# Testing Commands
echo "🧪 Test offline mode (in browser console):"
cat << 'EOF'

// Check offline manager status
offlineManager.getStatus()

// Simulate going offline
offlineManager.onOffline()

// Simulate going online
offlineManager.onOnline()

// Get all pending sales
const pending = await offlineManager.getPendingSales()
console.log(pending)

// Manually trigger sync
await offlineManager.checkAndSync()

// Clear all offline data
await offlineManager.clearAllData()

// Check service worker
navigator.serviceWorker.getRegistrations().then(regs => console.log(regs))
EOF

echo ""
echo "============================================"
echo ""

# Debugging Commands
echo "🔍 Debugging:"
cat << 'EOF'

# View IndexedDB data
# DevTools → Application → IndexedDB → quicksales_offline

# View Service Worker
# DevTools → Application → Service Workers

# View Network caching
# DevTools → Network → Size column (should show 'from ServiceWorker')

# View Cache Storage
# DevTools → Application → Cache Storage → quicksales-v1

# Monitor sync attempts (add to console)
setInterval(() => {
    fetch('/ims/api/sync-status/').then(r => r.json()).then(console.log)
}, 5000)
EOF

echo ""
echo "============================================"
echo "DEPLOYMENT CHECKLIST"
echo "============================================"
echo ""

cat << 'EOF'
Before Going to Production:

Database Setup
  □ Update Sale model with 3 new fields
  □ Run makemigrations
  □ Run migrate
  □ Verify columns created: sync_from_offline, original_temp_id, sync_timestamp

Frontend Setup
  □ Add Service Worker registration to base.html
  □ Add Offline Manager script
  □ Add Offline Indicator HTML
  □ Update store template with cache initialization

Testing
  □ Test offline mode with DevTools
  □ Test sync when coming online
  □ Test conflict resolution
  □ Test on mobile browsers
  □ Monitor sync errors in production

Monitoring
  □ Set up logging for sync errors
  □ Monitor database queries for sync
  □ Track offline session metrics
  □ Monitor Service Worker errors

Documentation
  □ Train staff on offline mode
  □ Document support procedures
  □ Create troubleshooting guide
  □ Update employee handbook
EOF

echo ""
echo "============================================"
echo "QUICK FILE REFERENCE"
echo "============================================"
echo ""

cat << 'EOF'
Core Files Created:

1. /ImsV3/static/assets/js/offline-manager.js (500 lines)
   - Main offline functionality
   - IndexedDB management
   - Sync logic

2. /ImsV3/static/assets/js/service-worker.js (250 lines)
   - Network interception
   - Asset caching
   - Offline fallbacks

3. /ims/api/offline_sync.py (200 lines)
   - Sync API endpoints
   - Conflict resolution
   - Data validation

4. /templates/partials/offline-indicator.html (100 lines)
   - Status indicator UI
   - Styling and animations

Documentation Files:

5. /OFFLINE_MODE_GUIDE.md (400+ lines)
   - Complete implementation guide
   - API documentation
   - Troubleshooting

6. /OFFLINE_SYNC_IMPLEMENTATION.md (150+ lines)
   - Architecture overview
   - System design

7. /OFFLINE_IMPLEMENTATION_SUMMARY.md (300+ lines)
   - Quick reference
   - Testing checklist
   - Deployment steps

8. /MIGRATION_INSTRUCTIONS.md (50 lines)
   - Database changes
   - Migration commands

Modified Files:

9. /ims/urls.py
   - Added 3 new API routes
   - Imported offline_sync functions
EOF

echo ""
echo "============================================"
echo "SUPPORT CONTACTS"
echo "============================================"
echo ""

cat << 'EOF'
Issues?

1. Check browser console for errors
2. Review OFFLINE_MODE_GUIDE.md Troubleshooting
3. Check DevTools Network and Application tabs
4. Verify Service Worker is registered
5. Check IndexedDB for data
6. Review sync API response codes

Common Issues:

Service Worker not registering?
  - Check browser console errors
  - Verify file path is correct
  - Check browser supports Service Workers
  - Verify HTTPS in production

Offline data not syncing?
  - Check internet connection
  - Check API endpoint responds
  - Verify CSRF token
  - Check browser cache

Inventory conflicts?
  - Expected when syncing if stock sold elsewhere
  - User can adjust quantity and retry
  - Server inventory is source of truth
EOF

echo ""
echo "============================================"
echo "Implementation Complete! ✅"
echo "============================================"
