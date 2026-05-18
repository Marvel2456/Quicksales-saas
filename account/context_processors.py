from account.models import Notification, OrganizationMembership
from ims.models import Sale


def organization_role(request):
    """Provide user's role in the current active organization."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"org_role": None}
    
    # Get the active organization from middleware context
    organization = getattr(request, "organization", None)
    
    if not organization:
        # Fallback to user's default organization
        organization = getattr(user, "organization", None)
    
    if not organization:
        return {"org_role": None}
    
    # Try to get membership-based role first
    membership = OrganizationMembership.objects.filter(
        user=user,
        organization=organization,
        is_active=True,
    ).first()
    if membership:
        return {"org_role": membership.role}

    # Fallback to global user role for legacy users
    return {"org_role": getattr(user, "role", None)}


def active_branch(request):
    """Provide the currently active branch for sidebar navigation."""
    from ims.models import Branch
    
    active_branch_id = request.session.get('active_branch_id')
    active_branch_name = request.session.get('active_branch_name')
    
    branch_obj = None
    if active_branch_id:
        try:
            organization = getattr(request, "organization", None)
            if not organization:
                organization = getattr(request.user, "organization", None)
            
            if organization:
                branch_obj = Branch.objects.get(id=active_branch_id, organization=organization)
        except Branch.DoesNotExist:
            pass
    
    return {
        'active_branch': branch_obj,
        'active_branch_id': active_branch_id,
        'active_branch_name': active_branch_name,
    }


def notification_count(request):
    """Provide unread notification count and recent notifications for navbar."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {
            "unread_notification_count": 0,
            "recent_notifications": []
        }

    # Filter notifications by current organization
    organization = getattr(request, "organization", None)
    if organization:
        notifications_qs = Notification.objects.filter(
            user=user,
            organization=organization
        )
    else:
        # Fallback: show all notifications if no organization context
        notifications_qs = Notification.objects.filter(user=user)
    
    unread_count = notifications_qs.filter(is_read=False).count()
    recent_notifications = notifications_qs.select_related('user')[:10]
    
    return {
        "unread_notification_count": unread_count,
        "recent_notifications": recent_notifications
    }


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
