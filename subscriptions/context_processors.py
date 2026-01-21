from django.conf import settings
from .utils import get_active_subscription, get_usage_stats, get_subscription_status


def paystack_public_key(request):
    return {"PAYSTACK_PUBLIC_KEY": settings.PAYSTACK_PUBLIC_KEY}


def subscription_context(request):
    """
    Add subscription information to all template contexts.
    """
    if not request.user.is_authenticated:
        return {}
    
    if not hasattr(request.user, 'organization') or not request.user.organization:
        return {}
    
    organization = request.user.organization
    subscription = get_active_subscription(organization)
    usage_stats = get_usage_stats(organization)
    status = get_subscription_status(organization)
    
    return {
        'active_subscription': subscription,
        'subscription_status': status,
        'usage_stats': usage_stats,
        'can_create_user': usage_stats['users']['can_create'],
        'can_create_branch': usage_stats['branches']['can_create'],
        'can_create_product': usage_stats['products']['can_create'],
    }
