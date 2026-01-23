from account.models import Notification
from ims.models import Sale


def notification_count(request):
    """Provide unread notification count for navbar badge across all pages."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"unread_notification_count": 0}

    unread_count = Notification.objects.filter(user=user, is_read=False).count()
    
    return {"unread_notification_count": unread_count}


def cart_count(request):
    """Provide cart item count across all pages."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"cart_item_count": 0}
    
    # Get all active open sales for the user across all branches
    open_sales = Sale.objects.filter(
        staff=user,
        completed=False,
        cancelled=False,
    )
    
    # Sum items from all open sales
    total_items = sum(sale.get_cart_items for sale in open_sales)
    
    return {"cart_item_count": total_items}
