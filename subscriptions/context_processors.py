from django.conf import settings
import logging
from .utils import get_active_subscription, get_usage_stats, get_subscription_status


logger = logging.getLogger(__name__)


def squadco_public_key(request):
    try:
        return {"SQUAD_PUBLIC_KEY": settings.SQUAD_PUBLIC_KEY}
    except Exception:
        logger.exception("squadco_public_key context processor failed")
        return {"SQUAD_PUBLIC_KEY": ""}


def subscription_context(request):
    """
    Add subscription information to all template contexts.
    """
    try:
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return {}
        
        organization = getattr(request, 'organization', None) or getattr(request.user, 'organization', None)
        if not organization:
            return {}
        
        subscription = get_active_subscription(organization)
        usage_stats = get_usage_stats(organization)
        status = get_subscription_status(organization)
        disable_store_sidebar = bool(
            subscription
            and subscription.plan
            and getattr(subscription.plan, 'disable_store', False)
        )
        
        return {
            'active_subscription': subscription,
            'subscription_status': status,
            'usage_stats': usage_stats,
            'can_create_user': usage_stats['users']['can_create'],
            'can_create_branch': usage_stats['branches']['can_create'],
            'can_create_product': usage_stats['products']['can_create'],
            'disable_store_sidebar': disable_store_sidebar,
        }
    except Exception:
        logger.exception("subscription_context processor failed")
        return {
            'active_subscription': None,
            'subscription_status': {
                'is_active': False,
                'message': 'Unavailable',
                'plan_name': 'Unknown',
                'days_remaining': 0,
            },
            'usage_stats': {
                'users': {'current': 0, 'limit': 0, 'percentage': 0, 'can_create': False},
                'branches': {'current': 0, 'limit': 0, 'percentage': 0, 'can_create': False},
                'products': {'current': 0, 'limit': 0, 'percentage': 0, 'can_create': False},
                'plan_name': 'Unknown',
            },
            'can_create_user': False,
            'can_create_branch': False,
            'can_create_product': False,
            'disable_store_sidebar': False,
        }
