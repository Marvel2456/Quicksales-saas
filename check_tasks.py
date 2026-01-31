#!/usr/bin/env python
import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ImsV3.settings")
django.setup()

from django_celery_beat.models import PeriodicTask, IntervalSchedule
from account.models import Notification
from subscriptions.models import Subscription
from django.utils import timezone

print("\n" + "="*90)
print("CELERY BEAT PERIODIC TASKS CONFIGURATION")
print("="*90)

# Check periodic tasks
tasks = PeriodicTask.objects.all()
print(f"\n✅ Total Periodic Tasks Registered: {tasks.count()}\n")

if tasks.exists():
    for i, task in enumerate(tasks, 1):
        print(f"{i}. Task Name: {task.name}")
        print(f"   Task Path: {task.task}")
        print(f"   Enabled: {'✅ Yes' if task.enabled else '❌ No'}")
        if task.interval:
            print(f"   Interval: Every {task.interval.every} {task.interval.get_period_display().lower()}")
        print(f"   Last Run: {task.last_run_at or 'Never'}")
        print(f"   Total Runs: {task.total_run_count}")
        print()
else:
    print("⚠️  WARNING: NO PERIODIC TASKS REGISTERED!")
    print("\n   You need to run these management commands:")
    print("   1. python manage.py schedule_subscription_reminders")
    print("   2. python manage.py schedule_trial_reminders (if it exists)")
    print()

print("="*90)
print("INTERVAL SCHEDULES AVAILABLE")
print("="*90 + "\n")

schedules = IntervalSchedule.objects.all()
print(f"Total Schedules: {schedules.count()}\n")

if schedules.exists():
    for schedule in schedules:
        print(f"Schedule ID: {schedule.id}")
        print(f"Interval: Every {schedule.every} {schedule.get_period_display().lower()}")
        print(f"Tasks using this schedule: {schedule.periodictask_set.count()}")
        print()
else:
    print("No interval schedules found.\n")

# Check Celery configuration
print("="*90)
print("CELERY CONFIGURATION")
print("="*90 + "\n")

from django.conf import settings
print(f"CELERY_BROKER_URL: {settings.CELERY_BROKER_URL}")
print(f"CELERY_RESULT_BACKEND: {settings.CELERY_RESULT_BACKEND}")
print(f"CELERY_BEAT_SCHEDULER: {settings.CELERY_BEAT_SCHEDULER}")
print()

# Check task status
print("="*90)
print("TASK REGISTRY & STATUS CHECK")
print("="*90 + "\n")

from celery import current_app

registered_tasks = current_app.tasks.keys()
task_names = [
    "deactivate_subscription",
    "send_trial_expiry_reminders",
    "send_subscription_expiry_reminders"
]

print(f"Looking for {len(task_names)} key tasks:\n")
for task_name in task_names:
    full_name = f"account.tasks.{task_name}"
    if full_name in registered_tasks:
        print(f"✅ {task_name}")
        print(f"   Full name: {full_name}")
    else:
        print(f"❌ {task_name}")
        print(f"   Full name: {full_name} - NOT FOUND")
    print()

print("="*90)
print("DATABASE RECORDS CHECK")
print("="*90 + "\n")

# Count database records
try:
    subscriptions = Subscription.objects.filter(is_active=True).count()
    notifications = Notification.objects.count()
    print(f"Active Subscriptions: {subscriptions}")
    print(f"Total Notifications: {notifications}")
    
    # Check subscriptions expiring soon
    now = timezone.now()
    from datetime import timedelta
    window_end = now + timedelta(days=3)
    expiring_soon = Subscription.objects.filter(
        is_active=True,
        end_date__gte=now,
        end_date__lte=window_end,
    ).count()
    print(f"Subscriptions expiring in 3 days: {expiring_soon}")
    print()
except Exception as e:
    print(f"Error checking database: {e}\n")

print("="*90)
print("SUMMARY & RECOMMENDATIONS")
print("="*90 + "\n")

if tasks.count() < 3:
    print("⚠️  MISSING PERIODIC TASKS!")
    print("\nTo set up all tasks, run these commands in your container:")
    print("\n  docker-compose exec web python manage.py schedule_subscription_reminders")
    print("  docker-compose exec web python manage.py schedule_trial_reminders")
    print("\n")
else:
    print("✅ All periodic tasks are registered!")
    print("\nEnsure Celery Beat is running:")
    print("  docker-compose logs celery-beat -f")
    print("\nEnsure Celery Worker is running:")
    print("  docker-compose logs celery -f")
    print("\n")

print("="*90)
