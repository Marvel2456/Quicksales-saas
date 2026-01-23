from django.core.management.base import BaseCommand
from ims.models import Inventory
from account.models import Notification
from django.db.models import F


class Command(BaseCommand):
    help = 'Test email sending for low stock by creating a low stock situation'

    def handle(self, *args, **options):
        self.stdout.write('=' * 70)
        self.stdout.write('TESTING EMAIL SENDING FOR LOW STOCK ALERTS')
        self.stdout.write('=' * 70)
        
        # Clear existing test notifications first
        self.stdout.write('\nClearing old test notifications...')
        deleted_count = Notification.objects.filter(
            notification_type='warning',
            message__icontains='Low stock alert'
        ).delete()[0]
        self.stdout.write(f'  Deleted {deleted_count} old notifications')
        
        # Find an inventory item with reorder level
        inventory = Inventory.objects.filter(
            reorder_level__isnull=False
        ).select_related('product', 'branch', 'organization').first()
        
        if not inventory:
            self.stdout.write(self.style.ERROR('\n✗ No inventory items with reorder level found!'))
            self.stdout.write('  Please set reorder levels in the admin panel first.')
            return
        
        self.stdout.write(f'\n📦 Test Product: {inventory.product.product_name}')
        self.stdout.write(f'   Branch: {inventory.branch.name}')
        self.stdout.write(f'   Current Quantity: {inventory.quantity}')
        self.stdout.write(f'   Reorder Level: {inventory.reorder_level}')
        
        # Save current quantity
        original_qty = inventory.quantity
        
        # Set to low stock
        self.stdout.write(f'\n🔄 Setting quantity to {inventory.reorder_level - 5} (below reorder level)...')
        inventory.quantity = max(0, inventory.reorder_level - 5)
        inventory.save()  # This triggers the signal
        
        self.stdout.write('\n⏳ Signal triggered... checking results...')
        
        # Check if notification was created
        notification = Notification.objects.filter(
            notification_type='warning',
            message__icontains=f'Low stock alert: {inventory.product.product_name}'
        ).first()
        
        if notification:
            self.stdout.write(self.style.SUCCESS('\n✓ Notification created successfully!'))
            self.stdout.write(f'  User: {notification.user.email}')
            self.stdout.write(f'  Message: {notification.message}')
            self.stdout.write(f'  Is Read: {notification.is_read}')
        else:
            self.stdout.write(self.style.ERROR('\n✗ No notification created'))
        
        # Check Docker logs for email
        self.stdout.write('\n📧 Email Status:')
        self.stdout.write('  Check Docker logs for email output:')
        self.stdout.write(self.style.WARNING('  docker logs quicksales 2>&1 | grep -A 50 "Subject: Low Stock Alert"'))
        
        # Restore original quantity
        self.stdout.write(f'\n🔄 Restoring quantity to {original_qty}...')
        inventory.quantity = original_qty
        inventory.save()  # This should auto-resolve the notification
        
        # Check if notification was marked as read
        if notification:
            notification.refresh_from_db()
            if notification.is_read:
                self.stdout.write(self.style.SUCCESS('\n✓ Notification auto-resolved (marked as read) when stock restored'))
            else:
                self.stdout.write(self.style.WARNING('\n⚠ Notification still unread'))
        
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('TEST COMPLETE'))
        self.stdout.write('=' * 70)
        self.stdout.write('\nNOTE: Emails are sent to console by default.')
        self.stdout.write('To send real emails, configure SMTP settings in .env file:')
        self.stdout.write('  EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend')
        self.stdout.write('  EMAIL_HOST=smtp.gmail.com')
        self.stdout.write('  EMAIL_PORT=587')
        self.stdout.write('  EMAIL_HOST_USER=your-email@gmail.com')
        self.stdout.write('  EMAIL_HOST_PASSWORD=your-app-password')
