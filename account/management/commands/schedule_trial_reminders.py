from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, IntervalSchedule
from django.utils import timezone


class Command(BaseCommand):
    help = 'Schedule the trial expiry reminder task to run every 24 hours'

    def handle(self, *args, **options):
        # Get or create a 24-hour interval schedule
        schedule, created = IntervalSchedule.objects.get_or_create(
            every=24,
            period=IntervalSchedule.HOURS,
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created new 24-hour schedule')
            )

        # Create or update the periodic task
        task, created = PeriodicTask.objects.update_or_create(
            name='Send Trial Expiry Reminders',
            defaults={
                'task': 'account.tasks.send_trial_expiry_reminders',
                'interval': schedule,
                'enabled': True,
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    '✅ Scheduled "Send Trial Expiry Reminders" task to run every 24 hours'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    '✅ Updated "Send Trial Expiry Reminders" task (already scheduled)'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n Task will run every 24 hours'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'   - Checks organizations with free trials'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'   - Sends reminder email 24 hours before trial expires'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'   - Creates notification on owner notification page'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✅ Command completed successfully!\n'
            )
        )
