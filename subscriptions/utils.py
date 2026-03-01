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
    return current_users < limits['max_users'], current_users, limits['max_users']


def can_create_branch(organization):
    """Check if organization can create more branches based on plan limit."""
    limits = get_plan_limits(organization)
    current_branches = Branch.objects.filter(organization=organization).count()
    return current_branches < limits['max_branches'], current_branches, limits['max_branches']


def can_create_product(organization):
    """Check if organization can create more products based on plan limit."""
    limits = get_plan_limits(organization)
    current_products = Product.objects.filter(organization=organization).count()
    return current_products < limits['max_products'], current_products, limits['max_products']


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
    
    return {
        'users': {
            'current': current_users,
            'limit': limits['max_users'],
            'percentage': (current_users / limits['max_users'] * 100) if limits['max_users'] > 0 else 0,
            'can_create': current_users < limits['max_users']
        },
        'branches': {
            'current': current_branches,
            'limit': limits['max_branches'],
            'percentage': (current_branches / limits['max_branches'] * 100) if limits['max_branches'] > 0 else 0,
            'can_create': current_branches < limits['max_branches']
        },
        'products': {
            'current': current_products,
            'limit': limits['max_products'],
            'percentage': (current_products / limits['max_products'] * 100) if limits['max_products'] > 0 else 0,
            'can_create': current_products < limits['max_products']
        },
        'plan_name': limits['plan_name']
    }
