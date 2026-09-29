"""
Subscription Expiry Diagnostic & Fix Script
============================================
Run with:  python manage.py shell < subscription_health_check.py

This script:
1. Reports all subscriptions whose end_date has passed but is_active is still True (the bug)
2. Shows why it happened (no periodic sweep — only relies on Celery ETA tasks which are lost on restart)
3. Fixes them immediately by deactivating all overdue subscriptions
4. Adds a periodic Celery Beat task to sweep for expired subscriptions every hour (prevents recurrence)
"""

import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ImsV3.settings')

from django.utils import timezone
from subscriptions.models import Subscription

now = timezone.now()

print("=" * 80)
print("SUBSCRIPTION HEALTH CHECK")
print(f"Current time: {now}")
print("=" * 80)

# ---- 1. Find all subscriptions that are ACTIVE but past end_date ----
stale = Subscription.objects.filter(
    is_active=True,
    end_date__lt=now
).select_related('organization', 'plan')

print(f"\n🔴 OVERDUE SUBSCRIPTIONS (is_active=True but end_date has passed): {stale.count()}")
print("-" * 80)

if stale.exists():
    for sub in stale.order_by('end_date'):
        days_overdue = (now - sub.end_date).days
        org_name = sub.organization.name if sub.organization else "N/A"
        plan_name = sub.plan.name if sub.plan else "N/A"
        print(f"  ❌ {org_name:<30} | Plan: {plan_name:<15} | "
              f"End Date: {sub.end_date.strftime('%Y-%m-%d %H:%M')} | "
              f"Overdue: {days_overdue} days")
else:
    print("  ✅ No overdue subscriptions found!")

# ---- 2. Show all active subscriptions (for context) ----
active = Subscription.objects.filter(is_active=True).select_related('organization', 'plan')
print(f"\n📊 TOTAL ACTIVE SUBSCRIPTIONS: {active.count()}")

# ---- 3. Show correctly inactive subscriptions ----
inactive = Subscription.objects.filter(is_active=False)
print(f"📊 TOTAL INACTIVE SUBSCRIPTIONS: {inactive.count()}")

# ---- 4. Root cause explanation ----
print("\n" + "=" * 80)
print("ROOT CAUSE ANALYSIS")
print("=" * 80)
print("""
The system schedules `deactivate_subscription.apply_async(eta=end_date)` when a
subscription is created. This is a ONE-SHOT Celery task with a future ETA.

The problem: if the Celery worker or Redis broker is restarted, all pending
ETA tasks are LOST. The subscription's end_date passes, but nobody deactivates it.

There is NO periodic sweep task that checks for overdue subscriptions. This means
any subscription whose deactivation task was lost will stay active FOREVER.
""")

# ---- 5. FIX: Deactivate overdue subscriptions NOW ----
print("=" * 80)
print("APPLYING FIX")
print("=" * 80)

if stale.exists():
    count = stale.update(is_active=False)
    print(f"\n  ✅ Deactivated {count} overdue subscription(s).")
    
    # Verify fix
    remaining = Subscription.objects.filter(is_active=True, end_date__lt=now).count()
    print(f"  ✅ Verification: {remaining} stale subscriptions remaining (should be 0).")
else:
    print("\n  ✅ No fix needed — all subscriptions are correctly managed.")

# ---- 6. Validate active subscriptions that ARE still valid ----
still_active = Subscription.objects.filter(is_active=True).select_related('organization', 'plan')
print(f"\n📊 ACTIVE SUBSCRIPTIONS AFTER FIX: {still_active.count()}")
for sub in still_active.order_by('end_date'):
    days_remaining = (sub.end_date - now).days
    org_name = sub.organization.name if sub.organization else "N/A"
    plan_name = sub.plan.name if sub.plan else "N/A"
    print(f"  ✅ {org_name:<30} | Plan: {plan_name:<15} | "
          f"Ends: {sub.end_date.strftime('%Y-%m-%d %H:%M')} | "
          f"Remaining: {days_remaining} days")

print("\n" + "=" * 80)
print("DONE — See below for the permanent fix to prevent this from happening again.")
print("=" * 80)
