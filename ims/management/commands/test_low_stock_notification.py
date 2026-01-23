from django.core.management.base import BaseCommand
from ims.models import Inventory
from account.models import Notification
from django.db.models import F


class Command(BaseCommand):
    help = 'Test low stock notification by creating test notifications'

    def handle(self, *args, **options):
        self.stdout.write("Checking for low stock items...")
        
        # Find inventory items where quantity <= reorder_level
        low_stock_items = Inventory.objects.filter(
            quantity__isnull=False,
            reorder_level__isnull=False,
            quantity__lte=F('reorder_level')
        ).select_related('product', 'branch', 'organization')
        
        self.stdout.write(f"Found {low_stock_items.count()} low stock items")
        
        if low_stock_items.count() == 0:
            # Create a test low stock item
            self.stdout.write("\nNo low stock items found. Checking inventory with reorder levels...")
            
            inventory_with_reorder = Inventory.objects.filter(
                reorder_level__isnull=False
            ).select_related('product', 'branch', 'organization').first()
            
            if inventory_with_reorder:
                self.stdout.write(f"\nTest: Temporarily setting {inventory_with_reorder.product.product_name} to low stock")
                original_qty = inventory_with_reorder.quantity
                
                # Set to below reorder level
                inventory_with_reorder.quantity = max(0, inventory_with_reorder.reorder_level - 5)
                inventory_with_reorder.save()
                
                self.stdout.write(f"  Product: {inventory_with_reorder.product.product_name}")
                self.stdout.write(f"  Branch: {inventory_with_reorder.branch.name}")
                self.stdout.write(f"  Quantity: {inventory_with_reorder.quantity}")
                self.stdout.write(f"  Reorder Level: {inventory_with_reorder.reorder_level}")
                
                # Create notification
                organization = inventory_with_reorder.organization or inventory_with_reorder.branch.organization
                owner = organization.owned_by
                
                if owner:
                    message = f"Low stock alert: {inventory_with_reorder.product.product_name} in {inventory_with_reorder.branch.name} is at {inventory_with_reorder.quantity} units (reorder: {inventory_with_reorder.reorder_level})"
                    
                    notification, created = Notification.objects.get_or_create(
                        user=owner,
                        message=message,
                        notification_type='warning',
                        defaults={'is_read': False}
                    )
                    
                    if created:
                        self.stdout.write(self.style.SUCCESS(f"\n✓ Notification created for {owner.email}"))
                    else:
                        self.stdout.write(self.style.WARNING(f"\n⚠ Notification already exists"))
                    
                    # Count notifications
                    unread_count = Notification.objects.filter(user=owner, is_read=False).count()
                    self.stdout.write(f"\nUnread notifications for {owner.email}: {unread_count}")
                    
                    # Restore original quantity
                    inventory_with_reorder.quantity = original_qty
                    inventory_with_reorder.save()
                    self.stdout.write(f"\nRestored quantity to {original_qty}")
                else:
                    self.stdout.write(self.style.ERROR("No owner found for organization"))
            else:
                self.stdout.write(self.style.ERROR("\nNo inventory items with reorder level set!"))
                self.stdout.write("Please set reorder levels in the admin panel first.")
        else:
            # Process existing low stock items
            for inventory in low_stock_items[:5]:  # Process first 5
                organization = inventory.organization or inventory.branch.organization
                owner = organization.owned_by
                
                if owner:
                    message = f"Low stock alert: {inventory.product.product_name} in {inventory.branch.name} is at {inventory.quantity} units (reorder: {inventory.reorder_level})"
                    
                    notification, created = Notification.objects.get_or_create(
                        user=owner,
                        message=message,
                        notification_type='warning',
                        defaults={'is_read': False}
                    )
                    
                    self.stdout.write(f"\n  Product: {inventory.product.product_name}")
                    self.stdout.write(f"  Status: {'Created' if created else 'Already exists'}")
                    
            # Count all notifications
            all_users = set([item.organization.owned_by or item.branch.organization.owned_by for item in low_stock_items if item.organization or item.branch])
            for user in all_users:
                if user:
                    unread_count = Notification.objects.filter(user=user, is_read=False).count()
                    self.stdout.write(f"\n{user.email}: {unread_count} unread notifications")
        
        self.stdout.write(self.style.SUCCESS("\n\nDone! Check the bell icon in the navbar."))
