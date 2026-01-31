# Subscription Expiry Reminder Feature

## Overview
This feature automatically sends email reminders and in-app notifications to organization owners when their subscription is about to expire (3 days before expiration).

## Implementation Details

### What Was Already Implemented
- ✅ Trial expiry reminders (`send_trial_expiry_reminders` task) - sends reminders 24 hours before trial ends
- ✅ Notification model with support for different types (success, error, warning, info)
- ✅ Email template for subscription renewal (`subscription_renewal_email.html`)
- ✅ Email sending function (`send_subscription_renewal_email`)

### What Was Added
- ✅ New Celery task: `send_subscription_expiry_reminders` (in `account/tasks.py`)
- ✅ Management command to schedule the task: `schedule_subscription_reminders`
- ✅ Runs every 6 hours to check for subscriptions expiring within 3 days
- ✅ Creates in-app notification on owner's notification page
- ✅ Sends email reminder with renewal link
- ✅ Deduplication to prevent spamming (checks for recent reminders)

## Files Modified/Created

### New Files
- `account/management/commands/schedule_subscription_reminders.py` - Command to register periodic task
- `account/management/__init__.py` - Django management module init
- `account/management/commands/__init__.py` - Django management commands module init

### Modified Files
- `account/tasks.py` - Added `send_subscription_expiry_reminders` task

## How It Works

1. **Task Scheduling**
   ```bash
   python manage.py schedule_subscription_reminders
   ```
   This registers the task in Celery Beat to run every 6 hours

2. **Automatic Execution**
   The Celery Beat scheduler automatically runs every 6 hours and:
   - Checks all active subscriptions
   - Identifies ones expiring within 3 days
   - Creates a notification on the owner's notification page
   - Sends an email reminder with renewal link
   - Deduplicates to avoid multiple reminders in the same 3-day period

3. **Notification Details**
   - **Type**: Warning
   - **Message**: "Subscription expiring soon: [Plan Name] for [Organization] expires in [X] day(s) on [Date]"
   - **Email**: Includes renewal link to subscription settings page
   - **Deduplication**: Checks if owner already received a reminder in the last 3 days

## Task Details

```python
@shared_task(name="send_subscription_expiry_reminders", bind=True, max_retries=3)
def send_subscription_expiry_reminders(self):
    """
    Send a reminder email and in-app notification to org owners whose 
    subscription ends within 3 days.
    """
```

### Parameters
- **Run Frequency**: Every 6 hours
- **Reminder Window**: 3 days before expiration
- **Max Retries**: 3 attempts if it fails
- **Deduplication**: 3-day window (won't send duplicate reminders within 3 days)

## Setup Instructions

### 1. Run Django Migrations (if needed)
```bash
python manage.py migrate
```

### 2. Register the Periodic Task
```bash
docker-compose exec web python manage.py schedule_subscription_reminders
```

Or manually in Django shell:
```python
python manage.py shell
from django_celery_beat.models import PeriodicTask, IntervalSchedule

schedule, created = IntervalSchedule.objects.get_or_create(
    every=6,
    period=IntervalSchedule.HOURS,
)

PeriodicTask.objects.update_or_create(
    name='Send Subscription Expiry Reminders',
    defaults={
        'task': 'account.tasks.send_subscription_expiry_reminders',
        'interval': schedule,
        'enabled': True,
    }
)
```

### 3. Ensure Celery Beat is Running
```bash
docker-compose up celery-beat
```

## Testing

### Test the Task Manually
```bash
docker-compose exec web python manage.py shell
from account.tasks import send_subscription_expiry_reminders
send_subscription_expiry_reminders()
```

### Check Celery Beat Schedule
In Django admin, go to:
- **DJANGO CELERY BEAT** → **Periodic tasks**
- Look for "Send Subscription Expiry Reminders"
- Verify it's enabled with 6-hour interval

### Monitor Execution
```bash
docker-compose logs celery-beat -f
```

## Email Template

Located at: `templates/account/emails/subscription_renewal_email.html`

The email includes:
- User greeting
- Subscription expiration date
- Call-to-action to renew
- Link to subscription settings page

## Notification Storage

Notifications are stored in the database and visible in:
- Django admin: `/admin/account/notification/`
- Frontend: User's notification page

## Logging

The task logs important events:
```
- INFO: "Sent subscription renewal reminder to {email} for {org_name}"
- ERROR: "Subscription reminder email failed for {email}: {error}"
- ERROR: "Error in send_subscription_expiry_reminders: {error}"
```

View logs:
```bash
docker-compose logs web -f | grep "subscription"
```

## Database Queries

The task uses:
- `Subscription.objects.filter(is_active=True, end_date__gte=now, end_date__lte=window_end)`
- `Notification.objects.filter(user=owner, created_at__gte=now - timedelta(days=3))`

Both use `select_related()` for optimization.

## Customization

### Change Reminder Window
In `account/tasks.py`, line with `window_end = now + timedelta(days=3)`:
- Change `3` to desired number of days

### Change Run Frequency
In `schedule_subscription_reminders.py`, change the interval:
```python
schedule, created = IntervalSchedule.objects.get_or_create(
    every=6,  # Change this (6 hours)
    period=IntervalSchedule.HOURS,
)
```

Options for period:
- `IntervalSchedule.HOURS`
- `IntervalSchedule.DAYS`
- `IntervalSchedule.WEEKS`

### Change Deduplication Window
In `account/tasks.py`, change the timedelta:
```python
created_at__gte=now - timedelta(days=3),  # Change this (3 days)
```

## Troubleshooting

### Task Not Running
1. Check Celery Beat is running: `docker-compose logs celery-beat`
2. Check task is registered: Django admin → Periodic tasks
3. Check Celery worker is running: `docker-compose logs celery`

### Emails Not Sending
1. Check email configuration in `ImsV3/settings.py`
2. Check `DEFAULT_FROM_EMAIL` is set
3. Check SMTP credentials if using external service
4. View logs: `docker-compose logs web | grep -i email`

### Notifications Not Appearing
1. Check database: `django-admin dbshell` → `SELECT * FROM account_notification;`
2. Verify user relationship is correct
3. Check notification_type is 'warning'

## Dependencies

- Django 4.0+
- Celery
- django-celery-beat
- django-celery-results

All are already installed in this project.

## Related Features

- **Trial Expiry Reminders**: `send_trial_expiry_reminders` (similar implementation)
- **Subscription Deactivation**: `deactivate_subscription` (runs when subscription expires)
- **Notifications Page**: `/account/notifications/` (displays all notifications)
- **Admin Interface**: `/admin/account/notification/` (manage notifications)

## Future Enhancements

Potential improvements:
1. Add SMS reminders
2. Configurable reminder days (owner can set when to be reminded)
3. Reminder history/audit log
4. Different reminder templates based on subscription type
5. Auto-renewal option
6. Grace period before deactivation

---

**Status**: ✅ Production Ready

**Last Updated**: January 28, 2026

**Maintained By**: Development Team
