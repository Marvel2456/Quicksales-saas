from django.utils import timezone
from .models import Subscription, Plan
from account.models import CustomUser, Branch
from ims.models import Product


def get_active_subscription(organization):
    """Get the active subscription for an organization."""
    return Subscription.objects.filter(
        organization=organization,
        is_active=True,
        end_date__gte=timezone.now()
    ).first()


def has_active_subscription(organization):
    """Check if organization has an active subscription."""
    subscription = get_active_subscription(organization)
    return subscription is not None


def has_online_store_access(organization):
    """
    Check if the organization has access to the online store feature
    based on their active subscription plan or trial status.
    """
    if not organization:
        return False

    subscription = get_active_subscription(organization)
    if subscription and subscription.plan:
        return bool(subscription.plan.has_online_store)

    if organization.trial_start and organization.trial_end:
        now = timezone.now()
        if organization.trial_start <= now <= organization.trial_end:
            return True

    return False


def get_plan_limits(organization):
    """Get the plan limits for an organization's active subscription."""
    subscription = get_active_subscription(organization)
    if subscription and subscription.plan:
        return {
            'max_users': subscription.plan.max_users,
            'max_branches': subscription.plan.max_branches,
            'max_products': subscription.plan.max_products,
            'plan_name': subscription.plan.name
        }
    # Default free plan limits
    return {
        'max_users': 1,
        'max_branches': 1,
        'max_products': 100,
        'plan_name': 'Free'
    }


def can_create_user(organization):
    """Check if organization can create more users based on plan limit."""
    from account.models import OrganizationMembership
    limits = get_plan_limits(organization)
    current_users = OrganizationMembership.objects.filter(organization=organization, is_active=True).count()
    max_users = limits['max_users']
    if max_users is not None and max_users > 5000:
        return True, current_users, None
    limit_val = max_users or 0
    return current_users < limit_val, current_users, limit_val


def can_create_branch(organization):
    """Check if organization can create more branches based on plan limit."""
    limits = get_plan_limits(organization)
    current_branches = Branch.objects.filter(organization=organization).count()
    return current_branches < limits['max_branches'], current_branches, limits['max_branches']


def can_create_product(organization):
    """Check if organization can create more products based on plan limit."""
    limits = get_plan_limits(organization)
    current_products = Product.objects.filter(organization=organization).count()
    max_products = limits['max_products']
    if max_products is not None and max_products > 5000:
        return True, current_products, None
    limit_val = max_products or 0
    return current_products < limit_val, current_products, limit_val


def get_subscription_status(organization):
    """Get detailed subscription status for an organization."""
    subscription = get_active_subscription(organization)
    
    if not subscription:
        return {
            'is_active': False,
            'message': 'No active subscription',
            'plan_name': 'Free',
            'days_remaining': 0
        }
    
    days_remaining = (subscription.end_date - timezone.now()).days
    
    return {
        'is_active': True,
        'subscription': subscription,
        'plan_name': subscription.plan.name if subscription.plan else 'Unknown',
        'days_remaining': days_remaining,
        'end_date': subscription.end_date,
        'message': f'{days_remaining} days remaining' if days_remaining > 0 else 'Expired'
    }


def get_usage_stats(organization):
    """Get current usage statistics compared to plan limits."""
    from account.models import OrganizationMembership
    limits = get_plan_limits(organization)
    
    current_users = OrganizationMembership.objects.filter(organization=organization, is_active=True).count()
    current_branches = Branch.objects.filter(organization=organization).count()
    current_products = Product.objects.filter(organization=organization).count()
    
    max_users = limits['max_users']
    users_unlimited = max_users is not None and max_users > 5000
    users_limit_num = max_users or 0

    max_products = limits['max_products']
    products_unlimited = max_products is not None and max_products > 5000
    products_limit_num = max_products or 0

    return {
        'users': {
            'current': current_users,
            'limit': 'Unlimited' if users_unlimited else users_limit_num,
            'is_unlimited': users_unlimited,
            'percentage': 0 if users_unlimited else ((current_users / users_limit_num * 100) if users_limit_num > 0 else 0),
            'can_create': True if users_unlimited else (current_users < users_limit_num)
        },
        'branches': {
            'current': current_branches,
            'limit': limits['max_branches'],
            'percentage': (current_branches / limits['max_branches'] * 100) if limits['max_branches'] > 0 else 0,
            'can_create': current_branches < limits['max_branches']
        },
        'products': {
            'current': current_products,
            'limit': 'Unlimited' if products_unlimited else products_limit_num,
            'is_unlimited': products_unlimited,
            'percentage': 0 if products_unlimited else ((current_products / products_limit_num * 100) if products_limit_num > 0 else 0),
            'can_create': True if products_unlimited else (current_products < products_limit_num)
        },
        'plan_name': limits['plan_name']
    }
