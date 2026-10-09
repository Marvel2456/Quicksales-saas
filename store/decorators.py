from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse
from account.utils import get_request_organization
from subscriptions.utils import has_online_store_access


def require_online_store_access(view_func):
    """
    Decorator to ensure the authenticated user's organization has a subscription
    plan that includes the Online Store feature.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        org = get_request_organization(request)
        if not org or not has_online_store_access(org):
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
                return JsonResponse({
                    'success': False,
                    'error': 'Online Store feature is not enabled on your current subscription plan. Please upgrade to access this feature.'
                }, status=403)

            messages.warning(
                request,
                "The Online Store feature is not included in your current subscription plan. Please upgrade your plan to access this feature."
            )
            return redirect('settings')

        return view_func(request, *args, **kwargs)
    return _wrapped_view
