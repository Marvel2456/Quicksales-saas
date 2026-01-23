from django.core.management.base import BaseCommand
from ims.models import Inventory
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test the low stock signal by updating an inventory item'

    def handle(self, *args, **kwargs):
        logger.info("=== Testing Low Stock Signal ===")
        self.stdout.write("Looking for inventory items to test...")
        
        # Get the first inventory item
        inventory = Inventory.objects.first()
        
        if not inventory:
            self.stdout.write(self.style.ERROR('No inventory items found'))
            return
        
        self.stdout.write(f"Testing with: {inventory.product.product_name}")
        self.stdout.write(f"Current quantity: {inventory.quantity}")
        self.stdout.write(f"Reorder level: {inventory.reorder_level}")
        
        # Save current values
        original_quantity = inventory.quantity
        
        # Set quantity below reorder level to trigger signal
        inventory.quantity = max(0, inventory.reorder_level - 1)
        self.stdout.write(f"Setting quantity to: {inventory.quantity}")
        
        # Save to trigger signal
        inventory.save()
        
        self.stdout.write(self.style.SUCCESS(f'Successfully saved inventory. Signal should have triggered.'))
        
        # Check if notification was created
        from account.models import Notification
        notifications = Notification.objects.filter(
            user=inventory.branch.organization.owner,
            message__icontains=inventory.product.product_name
        ).order_by('-created_at')[:1]
        
        if notifications.exists():
            self.stdout.write(self.style.SUCCESS(f'✓ Notification created: {notifications[0].message}'))
        else:
            self.stdout.write(self.style.WARNING('✗ No notification found'))
        
        # Restore original quantity
        inventory.quantity = original_quantity
        inventory.save()
        self.stdout.write(f"Restored quantity to: {original_quantity}")
