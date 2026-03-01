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
    """
    Add organization and branch context for authenticated users.
    Supports multi-organization memberships with session-based context switching.
    """
    def process_request(self, request):
        if not request.user.is_authenticated or request.user.is_superuser:
            request.organization = None
            request.branch = None
            return None
        
        # Get active organization from session
        active_org_id = request.session.get('active_organization_id')
        
        # Multi-org mode: Use memberships (PRIORITY over legacy FK)
        try:
            from account.models import OrganizationMembership
            
            # Try to get membership based on active_org_id in session
            if active_org_id:
                try:
                    membership = request.user.memberships.select_related(
                        'organization', 'branch'
                    ).get(
                        organization_id=active_org_id,
                        is_active=True
                    )
                    request.organization = membership.organization
                    request.branch = membership.branch
                    request.user._current_role = membership.role  # Store role for this request
                    return None
                except OrganizationMembership.DoesNotExist:
                    # Invalid org ID in session, clear it
                    if 'active_organization_id' in request.session:
                        del request.session['active_organization_id']
            
            # No active org in session, get first available membership
            first_membership = request.user.memberships.select_related(
                'organization', 'branch'
            ).filter(is_active=True).first()
            
            if first_membership:
                request.organization = first_membership.organization
                request.branch = first_membership.branch
                request.user._current_role = first_membership.role
                request.session['active_organization_id'] = str(first_membership.organization.id)
                return None
                
        except Exception:
            pass  # Fall through to legacy mode
        
        # Backward compatibility: If user has organization FK (legacy single-org) and NO memberships
        if hasattr(request.user, 'organization') and request.user.organization:
            request.organization = request.user.organization
            request.branch = request.user.branch
            # Save to session for consistency
            if not active_org_id:
                request.session['active_organization_id'] = str(request.user.organization.id)
            return None
        
        # User has no organization context at all
        request.organization = None
        request.branch = None
        return None

        return None
