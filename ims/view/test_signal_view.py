from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from ims.models import Inventory
from account.models import Notification
from django.contrib.auth.decorators import login_required
import logging

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def test_low_stock_signal_view(request):
    """Test view to manually trigger low stock signal"""
    
    # Get first inventory item with a reorder level
    inventory = Inventory.objects.filter(reorder_level__isnull=False).first()
    
    if not inventory:
        return JsonResponse({'error': 'No inventory items with reorder level found'}, status=404)
    
    # Save current quantity
    original_quantity = inventory.quantity
    logger.info(f"Original quantity: {original_quantity}")
    
    # Set quantity to trigger low stock
    inventory.quantity = max(0, inventory.reorder_level - 1)
    logger.info(f"Setting quantity to: {inventory.quantity} (reorder: {inventory.reorder_level})")
    
    # This should trigger the signal
    inventory.save()
    
    # Check if notification was created
    notification_count = Notification.objects.filter(
        user=inventory.branch.organization.owned_by,
        notification_type='warning',
        message__icontains=inventory.product.product_name
    ).count()
    
    # Restore quantity
    inventory.quantity = original_quantity
    inventory.save()
    
    return JsonResponse({
        'status': 'success',
        'product': inventory.product.product_name,
        'branch': inventory.branch.branch_name,
        'test_quantity': max(0, inventory.reorder_level - 1),
        'reorder_level': inventory.reorder_level,
        'notification_count': notification_count,
        'owner_email': inventory.branch.organization.owned_by.email if inventory.branch.organization.owned_by else None
    })
