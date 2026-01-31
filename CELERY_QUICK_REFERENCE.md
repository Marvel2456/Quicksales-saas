# Quick Reference: Celery Tasks Checklist

## ✅ What's Working

### Free Trial System
- [x] Trial end date set automatically on organization creation
- [x] `send_trial_expiry_reminders` task sends email 24 hours before expiry
- [x] Creates in-app notification on owner's notification page
- [x] Deactivates subscription at trial end via `deactivate_subscription` task
- [x] Scheduled to run every 24 hours automatically

### Paid Subscription System  
- [x] Subscription created when payment verified
- [x] Subscription end date set to 1 month/year from purchase
- [x] `send_subscription_expiry_reminders` task sends email 3 days before expiry
- [x] Creates in-app notification on owner's notification page
- [x] Deduplicates notifications (won't spam) using 3-day window
- [x] Scheduled to run every 6 hours automatically
- [x] `deactivate_subscription` task deactivates at end_date
- [x] Sends final "your subscription expired" email

### Infrastructure
- [x] Celery worker running (celery@...)
- [x] Celery Beat scheduler running
- [x] Redis broker connected
- [x] PostgreSQL database connected
- [x] Email system configured (Zoho SMTP)
- [x] Django Celery Beat database scheduler active

---

## 🎯 Task Quick Reference

```
TASK NAME: deactivate_subscription
├─ Type: On-demand (scheduled at subscription creation)
├─ Trigger: subscription.end_date
├─ Action: Sets is_active = False, sends email
├─ Retries: 3
└─ Status: ✅ Ready

TASK NAME: send_trial_expiry_reminders  
├─ Type: Periodic (scheduled by management command)
├─ Schedule: Every 24 hours
├─ Action: Email + notification 24hrs before trial end
├─ Retries: 3
└─ Status: ✅ Registered & Active

TASK NAME: send_subscription_expiry_reminders
├─ Type: Periodic (scheduled by management command)
├─ Schedule: Every 6 hours
├─ Action: Email + notification 3 days before expiry
├─ Retries: 3
├─ Dedup: Yes (3-day window)
└─ Status: ✅ Registered & Active
```

---

## 📊 Current Data

| Metric | Value |
|--------|-------|
| Active Subscriptions | 1 |
| Inactive Subscriptions | 3 |
| Organizations on Trial | 1 |
| Notifications Created | 1 |
| Tasks Scheduled | 2 |
| Workers Running | 1 |

---

## 🔍 Quick Status Checks

### Check if tasks are registered:
```bash
docker-compose exec web python check_tasks.py
```

### Detailed verification:
```bash
docker-compose exec web python verify_celery_tasks.py
```

### View Celery worker logs:
```bash
docker-compose logs celery -f
```

### View scheduler logs:
```bash
docker-compose logs celery-beat -f
```

### Check in Django admin:
Go to http://localhost:8000/admin/django_celery_beat/periodictask/
You should see:
- Send Trial Expiry Reminders (24-hour interval)
- Send Subscription Expiry Reminders (6-hour interval)

---

## 🚀 Manual Task Execution

### Test trial reminders:
```bash
docker-compose exec web python manage.py shell
>>> from account.tasks import send_trial_expiry_reminders
>>> send_trial_expiry_reminders.delay()
```

### Test subscription reminders:
```bash
docker-compose exec web python manage.py shell
>>> from account.tasks import send_subscription_expiry_reminders
>>> send_subscription_expiry_reminders.delay()
```

### Test deactivation (for a specific subscription):
```bash
docker-compose exec web python manage.py shell
>>> from account.tasks import deactivate_subscription
>>> deactivate_subscription.delay('subscription-id-here')
```

---

## 📧 Email Templates

All located in `templates/account/emails/`:
- `trial_expiry_email.html` - 24 hours before trial ends
- `trial_expired_email.html` - When trial/subscription expires
- `subscription_renewal_email.html` - 3 days before subscription ends

---

## ⚙️ Configuration Files

### Task Definitions
- File: `account/tasks.py`
- Functions: 3 (deactivate_subscription, send_trial_expiry_reminders, send_subscription_expiry_reminders)

### Management Commands
- File 1: `account/management/commands/schedule_trial_reminders.py`
- File 2: `account/management/commands/schedule_subscription_reminders.py`

### Celery Config
- File: `ImsV3/settings.py`
- Broker: Redis at `redis://redis:6379/0`
- Scheduler: DatabaseScheduler (django-celery-beat)

### Docker Services
- Worker: `docker-compose.yml` service `celery_worker`
- Beat: `docker-compose.yml` service `celery_beat`
- Broker: `docker-compose.yml` service `redis`

---

## 🐛 Troubleshooting Quick Fixes

### Tasks not running?
```bash
docker-compose restart celery celery-beat
docker-compose logs celery -f
```

### Emails not sending?
```bash
# Check SMTP settings in Django admin
# Check settings.py has EMAIL_* variables
# Test manually: python manage.py shell
>>> from django.core.mail import send_mail
>>> send_mail('Test', 'Body', 'from@example.com', ['to@example.com'])
```

### Notifications not appearing?
```bash
# Check database
docker-compose exec db psql -U quicksales_user -d quicksales
SELECT * FROM account_notification LIMIT 10;
```

### Worker crashed?
```bash
docker-compose logs celery | tail -50
docker-compose up -d celery
```

---

## 📋 Setup Done Checklist

- [x] Three task functions created (deactivate_subscription, send_trial_expiry_reminders, send_subscription_expiry_reminders)
- [x] Management command created for trial reminders (schedule_trial_reminders.py)
- [x] Management command created for subscription reminders (schedule_subscription_reminders.py)
- [x] Both management commands executed to register tasks
- [x] Periodic tasks registered in Celery Beat database
- [x] Interval schedules created (24-hour and 6-hour)
- [x] Celery worker running and responsive
- [x] Redis broker connected and working
- [x] Email configuration active
- [x] Templates in place
- [x] Database models ready
- [x] Verification scripts created

---

## 📚 Documentation

Created:
1. `CELERY_TASKS_STATUS.md` - Full detailed report
2. `SUBSCRIPTION_EXPIRY_REMINDERS.md` - Feature documentation
3. `check_tasks.py` - Quick status script
4. `verify_celery_tasks.py` - Comprehensive verification
5. This file - Quick reference

---

## ✅ System Status

**Overall**: ✅ **FULLY OPERATIONAL**

All tasks configured correctly, workers running, schedules active, emails ready to send.

---

Last verified: January 30, 2026
Next automatic checks: Every 6 hours (subscription reminders) and every 24 hours (trial reminders)
