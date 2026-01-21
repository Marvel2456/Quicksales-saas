from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone
from subscriptions.models import Subscription
from django.urls import reverse


class SubscriptionMiddleware:
    """
    Middleware to check subscription status on every request.
    Redirects to subscription page if subscription is expired.
    Excludes certain URLs like login, logout, subscription pages, etc.
    """
    
    # URLs that don't require active subscription
    EXEMPT_URLS = [
        '/account/login/',
        '/account/logout/',
        '/account/register/',
        '/account/verify-email/',
        '/account/password-reset/',
        '/subscriptions/settings/',
        '/subscriptions/plan/',
        '/subscriptions/webhook/',
        '/static/',
        '/media/',
        '/admin/',
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Skip check for exempt URLs
        if self._is_exempt(request.path):
            return self.get_response(request)
        
        # Skip check if user is not authenticated
        if not request.user.is_authenticated:
            return self.get_response(request)
        
        # Skip check if user has no organization
        if not hasattr(request.user, 'organization') or not request.user.organization:
            return self.get_response(request)
        
        # Check subscription status
        organization = request.user.organization
        subscription = Subscription.objects.filter(
            organization=organization,
            is_active=True,
            end_date__gte=timezone.now()
        ).first()
        
        # If no active subscription and not already on subscription page
        if not subscription and '/subscription/' not in request.path:
            # Check if there's an expired subscription
            expired_sub = Subscription.objects.filter(
                organization=organization,
                is_active=True,
                end_date__lt=timezone.now()
            ).first()
            
            if expired_sub:
                # Deactivate expired subscription
                expired_sub.is_active = False
                expired_sub.save()
                messages.warning(
                    request,
                    'Your subscription has expired. Please renew to continue accessing all features.'
                )
            else:
                messages.info(
                    request,
                    'Please select a subscription plan to continue.'
                )
            
            return redirect('settings')
        
        # Add subscription info to request for easy access in views
        if subscription:
            request.subscription = subscription
            request.plan = subscription.plan
        
        return self.get_response(request)
    
    def _is_exempt(self, path):
        """Check if the path is exempt from subscription check."""
        for exempt_url in self.EXEMPT_URLS:
            if path.startswith(exempt_url):
                return True
        return False
