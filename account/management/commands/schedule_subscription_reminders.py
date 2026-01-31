from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, IntervalSchedule
from django.utils import timezone


class Command(BaseCommand):
    help = 'Schedule the subscription expiry reminder task to run every 6 hours'

    def handle(self, *args, **options):
        # Get or create a 6-hour interval schedule
        schedule, created = IntervalSchedule.objects.get_or_create(
            every=6,
            period=IntervalSchedule.HOURS,
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created new 6-hour schedule')
            )

        # Create or update the periodic task
        task, created = PeriodicTask.objects.update_or_create(
            name='Send Subscription Expiry Reminders',
            defaults={
                'task': 'account.tasks.send_subscription_expiry_reminders',
                'interval': schedule,
                'enabled': True,
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    '✅ Scheduled "Send Subscription Expiry Reminders" task to run every 6 hours'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    '✅ Updated "Send Subscription Expiry Reminders" task (already scheduled)'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n📅 Task will run every 6 hours'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'   - Checks subscriptions expiring within 3 days'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'   - Sends email + notification to organization owner'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'   - Deduplicates to avoid spamming'
            )
        )
