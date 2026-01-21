from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect
from django.urls import reverse
from account.models import Organization


class ForcePasswordChangeMiddleware(MiddlewareMixin):
    """
    Middleware to redirect users who must change their password.
    Allows access only to force_password_change, logout, and static files.
    """
    def process_request(self, request):
        # Skip for unauthenticated users
        if not request.user.is_authenticated:
            return None
        
        # Skip if user doesn't need to change password
        if not request.user.must_change_password:
            return None
        
        # Allow access to these URLs even when password change is required
        allowed_urls = [
            reverse('force_password_change'),
            reverse('logout'),
            '/static/',
            '/media/',
        ]
        
        # Check if current path is allowed
        for url in allowed_urls:
            if request.path.startswith(url):
                return None
        
        # Redirect to force password change page
        return redirect('force_password_change')


# class SubdomainOrganizationMiddleware(MiddlewareMixin):
#     def process_request(self, request):
#         host = request.get_host().split(':')[0]  # remove port
#         parts = host.split('.')

#         if len(parts) < 3:
#             request.organization = None  # Root domain (e.g. landing page)
#             return

#         subdomain = parts[0]

#         try:
#             request.organization = Organization.objects.get(slug=subdomain)
#         except Organization.DoesNotExist:
#             return HttpResponse("Organization not found", status=404)


class SubdomainOrganizationMiddleware(MiddlewareMixin):
    def process_request(self, request):
        host = request.get_host().split(':')[0]
        parts = host.split('.')

        # Root domain (e.g., landing page or docs.yourapp.com)
        if len(parts) < 3:
            request.organization = None
            return

        subdomain = parts[0]

        try:
            request.organization = Organization.objects.get(slug=subdomain)
        except Organization.DoesNotExist:
            return HttpResponse("Organization not found", status=404)

        # Authorization check: ensure logged-in user's org matches the subdomain
        if request.user.is_authenticated:
            user_org = getattr(request.user, "organization", None)
            if user_org and user_org != request.organization:
                return HttpResponse("Organization mismatch", status=403)


class OrganizationContextMiddleware(MiddlewareMixin):
    """Add organization to template context for all authenticated users."""
    def process_request(self, request):
        if request.user.is_authenticated:
            request.organization = getattr(request.user, 'organization', None)
        return None