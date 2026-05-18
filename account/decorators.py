from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import user_passes_test
from .models import Branch, CustomUser, OrganizationMembership
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from functools import wraps
from django.contrib.auth.views import redirect_to_login
from django.contrib import messages
from django.urls import reverse
from account.utils import get_request_organization


def role_required(roles, redirect_field_name=REDIRECT_FIELD_NAME, login_url='login'):
    """
    Check organization-specific role from membership, fallback to global user role for legacy users.
    """
    def decorator(function):
        @wraps(function)
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated or not user.is_active:
                return redirect_to_login(request.get_full_path(), login_url, redirect_field_name)
            
            # Get the organization from middleware context
            organization = getattr(request, 'organization', None)
            
            if organization:
                # Multi-org mode: check membership role
                membership = user.memberships.filter(
                    organization_id=organization.id,
                    is_active=True,
                ).first()
                user_role = membership.role if membership else None
            else:
                # Legacy mode: use global user role
                user_role = user.role
            
            if user_role in roles:
                return function(request, *args, **kwargs)
            
            messages.error(request, f'You do not have permission to access this page. Required roles: {", ".join(roles)}')
            return redirect_to_login(request.get_full_path(), login_url, redirect_field_name)
        
        return _wrapped_view
    return decorator


# def role_required(roles, redirect_field_name=REDIRECT_FIELD_NAME, login_url='login'):
#     def decorator(view_func):
#         @wraps(view_func)
#         def _wrapped_view(request, *args, **kwargs):
#             user = request.user
#             if user.is_authenticated and user.is_active and user.role in roles:
#                 return view_func(request, *args, **kwargs)
#             return redirect_to_login(request.get_full_path(), login_url, redirect_field_name)
#         return _wrapped_view
#     return decorator



# def for_admin(function=None, redirect_field_name=REDIRECT_FIELD_NAME, login_url='login'):
#     actual_decorator = user_passes_test(
#         lambda u: u.is_active and u.role == 'owner',
#         login_url=login_url,
#         redirect_field_name=redirect_field_name
#     )
#     if function:
#         return actual_decorator(function)
#     return actual_decorator

# def for_sub_admin(function=None, redirect_field_name=REDIRECT_FIELD_NAME, login_url='login'):
#     actual_decorator = user_passes_test(
#         lambda u: u.is_active and u.role == 'manager',
#         login_url=login_url,
#         redirect_field_name=redirect_field_name
#     )
#     if function:
#         return actual_decorator(function)
#     return actual_decorator

# def for_staff(function=None, redirect_field_name=REDIRECT_FIELD_NAME, login_url='login'):
#     actual_decorator = user_passes_test(
#         lambda u: u.is_active and u.role == 'sales',
#         login_url=login_url,
#         redirect_field_name=redirect_field_name
#     )
#     if function:
#         return actual_decorator(function)
#     return actual_decorator


def subscription_required(function=None, redirect_url='settings'):
    """
    Decorator to check if the user's organization has an active subscription.
    Redirects to subscription page if no active subscription found.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), 'login')
            
            from subscriptions.utils import has_active_subscription
            
            if not hasattr(request.user, 'organization') or not request.user.organization:
                messages.error(request, 'You must be part of an organization to access this feature.')
                return redirect('settings')
            
            if not has_active_subscription(request.user.organization):
                messages.warning(request, 'Your subscription has expired. Please renew to continue using this feature.')
                return redirect(redirect_url)
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    
    if function:
        return decorator(function)
    return decorator


def check_user_limit(function):
    """
    Decorator to check if organization has reached max_users limit.
    Used on user/staff creation views.
    """
    @wraps(function)
    def wrapper(request, *args, **kwargs):
        if request.method == 'POST':
            from subscriptions.utils import can_create_user, get_plan_limits

            organization = get_request_organization(request) or getattr(request.user, "organization", None)
            if not organization:
                messages.error(request, 'You do not belong to any organization.')
                return redirect('login')
            can_create, current, limit = can_create_user(organization)
            
            if not can_create:
                limits = get_plan_limits(organization)
                messages.error(
                    request,
                    f'You have reached the maximum number of users ({limit}) for your {limits["plan_name"]} plan. '
                    f'Please upgrade your subscription to add more users.'
                )
                return redirect('settings')
        
        return function(request, *args, **kwargs)
    return wrapper


def check_branch_limit(function):
    """
    Decorator to check if organization has reached max_branches limit.
    Used on branch creation views.
    """
    @wraps(function)
    def wrapper(request, *args, **kwargs):
        if request.method == 'POST':
            from subscriptions.utils import can_create_branch, get_plan_limits

            organization = get_request_organization(request) or getattr(request.user, "organization", None)
            if not organization:
                messages.error(request, 'You do not belong to any organization.')
                return redirect('login')
            can_create, current, limit = can_create_branch(organization)
            
            if not can_create:
                limits = get_plan_limits(organization)
                messages.error(
                    request,
                    f'You have reached the maximum number of branches ({limit}) for your {limits["plan_name"]} plan. '
                    f'Please upgrade your subscription to add more branches.'
                )
                return redirect('settings')
        
        return function(request, *args, **kwargs)
    return wrapper


def check_product_limit(function):
    """
    Decorator to check if organization has reached max_products limit.
    Used on product creation views.
    """
    @wraps(function)
    def wrapper(request, *args, **kwargs):
        if request.method == 'POST':
            from subscriptions.utils import can_create_product, get_plan_limits

            organization = get_request_organization(request) or getattr(request.user, "organization", None)
            if not organization:
                messages.error(request, 'You do not belong to any organization.')
                return redirect('login')
            can_create, current, limit = can_create_product(organization)
            
            if not can_create:
                limits = get_plan_limits(organization)
                messages.error(
                    request,
                    f'You have reached the maximum number of products ({limit}) for your {limits["plan_name"]} plan. '
                    f'Please upgrade your subscription to add more products.'
                )
                return redirect('settings')
        
        return function(request, *args, **kwargs)
    return wrapper


# Old commented out decorators below
# def is_unsubscribed(function=None, redirect_field_name=REDIRECT_FIELD_NAME, login_url='login'):
#     actual_decorator = user_passes_test(
#         lambda u: u.is_active and u.is_subscribed==True,
#         login_url=login_url,
#         redirect_field_name=redirect_field_name
#     )
#     if function:
#         return actual_decorator(function)
#     return actual_decorator


# def branch_required(branch):
#     def decorator(view_func):
#         def wrapped_view(request, pk, *args, **kwargs):
#             if request.user.is_authenticated and request.user.is_admin==False:
#                 branch = Branch.objects.get(id=pk)
#                 user_branch = CustomUser.objects.filter(branch_id = pk)
#                 if user_branch.id == branch.id:
#                     return view_func(request, pk, *args, **kwargs)
#                 else:
#                     return redirect('/index/'+str(branch.id)) 
#             else:
#                 return redirect('login')
#         return wrapped_view
#     return decorator



        

# from django.shortcuts import redirect
# from django.contrib.auth.decorators import login_required

# def branch_required(desired_branch):
#     def decorator(view_func):
#         def wrapped_view(request, *args, **kwargs):
#             if request.user.is_authenticated:
#                 if request.user.branch == desired_branch:
#                     return view_func(request, *args, **kwargs)
#                 else:
#                     return redirect('unauthorized')
#             else:
#                 return redirect('login')
#         return wrapped_view
#     return decorator

# @branch_required('sales')
# @login_required
# def my_view(request):
#     # Code for the view goes here
#     pass


# from django.shortcuts import redirect
# from django.contrib.auth.decorators import login_required
# from your_app.models import Branch, CustomUser

# def branch_required(desired_branch_id):
#     def decorator(view_func):
#         def wrapped_view(request, *args, **kwargs):
#             if request.user.is_authenticated:
#                 user_branch = CustomUser.objects.get(id=request.user.id).branch
#                 if user_branch.id == desired_branch_id:
#                     return view_func(request, *args, **kwargs)
#                 else:
#                     return redirect('unauthorized')
#             else:
#                 return redirect('login')
#         return wrapped_view
#     return decorator

# @branch_required(1)
# @login_required
# def my_view(request):
#     # Code for the view goes here
#     pass
