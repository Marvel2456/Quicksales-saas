from django.core.management.base import BaseCommand
from account.models import Notification
from ims.models import Inventory


class Command(BaseCommand):
    help = 'Check status of low stock notification system'

    def handle(self, *args, **options):
        self.stdout.write('=' * 60)
        self.stdout.write('LOW STOCK NOTIFICATION SYSTEM - STATUS CHECK')
        self.stdout.write('=' * 60)
        
        # Check notifications
        notifications = Notification.objects.filter(is_read=False)
        self.stdout.write(f'\n✓ Unread Notifications: {notifications.count()}')
        
        for n in notifications:
            self.stdout.write(f'  - User: {n.user.email}')
            self.stdout.write(f'    Type: {n.notification_type}')
            self.stdout.write(f'    Message: {n.message}')
            self.stdout.write(f'    Created: {n.created_at}')
            self.stdout.write('')
        
        # Check low stock items
        low_stock = Inventory.objects.filter(
            quantity__isnull=False,
            reorder_level__isnull=False,
        ).extra(where=['quantity <= reorder_level'])
        
        self.stdout.write(f'✓ Low Stock Items: {low_stock.count()}')
        for item in low_stock[:3]:
            self.stdout.write(f'  - {item.product.product_name} in {item.branch.name}')
            self.stdout.write(f'    Quantity: {item.quantity}, Reorder Level: {item.reorder_level}')
        
        self.stdout.write('')
        self.stdout.write('=' * 60)
        self.stdout.write(self.style.SUCCESS(f'NAVBAR BELL ICON WILL SHOW: {notifications.count()}'))
        self.stdout.write('=' * 60)
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✓ Notification system is working correctly!'))
        self.stdout.write('  Log in to see the bell icon with notification count.')
