from account.models import Notification, OrganizationMembership
from ims.models import Sale
from django.core.exceptions import ValidationError
import logging


logger = logging.getLogger(__name__)


def organization_role(request):
    """Provide user's role in the current active organization."""
    try:
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
    except Exception:
        logger.exception("organization_role context processor failed")
        return {"org_role": None}


def active_branch(request):
    """Provide the currently active branch for sidebar navigation."""
    from ims.models import Branch
    
    try:
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
            except (Branch.DoesNotExist, ValidationError, ValueError, TypeError):
                # Clear stale or malformed branch IDs to avoid repeat 500s on subsequent requests.
                request.session.pop('active_branch_id', None)
                request.session.pop('active_branch_name', None)
                pass
        
        return {
            'active_branch': branch_obj,
            'active_branch_id': active_branch_id,
            'active_branch_name': active_branch_name,
        }
    except Exception:
        logger.exception("active_branch context processor failed")
        return {
            'active_branch': None,
            'active_branch_id': None,
            'active_branch_name': None,
        }


def notification_count(request):
    """Provide unread notification count and recent notifications for navbar."""
    try:
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
    except Exception:
        logger.exception("notification_count context processor failed")
        return {
            "unread_notification_count": 0,
            "recent_notifications": []
        }


def cart_count(request):
    """Provide cart item count across all pages."""
    try:
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
    except Exception:
        logger.exception("cart_count context processor failed")
        return {"cart_item_count": 0}
