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
    # Public and authentication URLs exempt from organization mismatch check
    EXEMPT_URLS = [
        '/account/login/',
        '/account/logout/',
        '/account/register/',
        '/account/verify-email/',
        '/account/resend-verification/',
        '/account/forgot-password/',
        '/account/reset-password/',
        '/account/api/check-email/',
        '/account/api/session-check/',
        '/account/organizations/',
        '/store/',
        '/buyer/',
        '/static/',
        '/media/',
        '/admin/',
    ]

    def process_request(self, request):
        host = request.get_host().split(':')[0]
        parts = host.split('.')

        # Root domain (e.g., landing page or docs.yourapp.com)
        if len(parts) < 3:
            request.organization = None
            return None

        subdomain = parts[0]

        # Ignore generic subdomains
        if subdomain in ['www', 'app', 'api', 'mail']:
            request.organization = None
            return None

        try:
            request.organization = Organization.objects.get(slug=subdomain)
        except Organization.DoesNotExist:
            return HttpResponse("Organization not found", status=404)

        # Allow exempt URLs without authorization mismatch blocking
        for exempt_url in self.EXEMPT_URLS:
            if request.path.startswith(exempt_url):
                return None

        # Superusers bypass tenant organization boundaries
        if request.user.is_authenticated and request.user.is_superuser:
            return None

        # Authorization check: ensure logged-in user has valid membership/ownership in this subdomain org
        if request.user.is_authenticated:
            user = request.user
            has_access = (
                user.memberships.filter(organization=request.organization, is_active=True).exists() or
                user.owned_organizations.filter(id=request.organization.id).exists() or
                getattr(user, "organization", None) == request.organization
            )

            if has_access:
                request.session['active_organization_id'] = str(request.organization.id)
                return None
            else:
                # User is logged in but trying to access a subdomain belonging to another organization.
                # Redirect them to their own active organization's subdomain.
                from django.conf import settings
                from account.emails import get_protocol

                user_membership = user.memberships.filter(is_active=True).select_related('organization').first()
                user_org = (
                    user_membership.organization if user_membership
                    else (user.owned_organizations.first() or getattr(user, "organization", None))
                )

                if user_org and user_org.slug and user_org.slug != subdomain:
                    protocol = get_protocol()
                    target_path = request.get_full_path()
                    return redirect(f"{protocol}://{user_org.slug}.{settings.DOMAIN}{target_path}")

                return HttpResponse("Organization mismatch", status=403)


class OrganizationContextMiddleware(MiddlewareMixin):
    """
    Add organization and branch context for authenticated users.
    Supports multi-organization memberships with session-based context switching.
    """
    def process_request(self, request):
        if not request.user.is_authenticated or request.user.is_superuser:
            request.organization = getattr(request, 'organization', None)
            request.branch = None
            return None
        
        # If subdomain already provided organization context, honor and align with it
        subdomain_org = getattr(request, 'organization', None)
        active_org_id = str(subdomain_org.id) if subdomain_org else request.session.get('active_organization_id')
        
        # Multi-org mode: Use memberships (PRIORITY over legacy FK)
        try:
            from account.models import OrganizationMembership
            
            # Try to get membership based on active_org_id
            if active_org_id:
                membership = request.user.memberships.select_related(
                    'organization', 'branch'
                ).filter(
                    organization_id=active_org_id,
                    is_active=True,
                ).first()
                if membership:
                    request.organization = membership.organization
                    request.branch = membership.branch
                    request.user._current_role = membership.role  # Store role for this request
                    request.session['active_organization_id'] = str(membership.organization.id)
                    return None

                # Invalid org ID in session, clear it if not from subdomain
                if not subdomain_org and 'active_organization_id' in request.session:
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
            if not request.session.get('active_organization_id'):
                request.session['active_organization_id'] = str(request.user.organization.id)
            return None
        
        # Fallback to subdomain org if set, else None
        request.organization = subdomain_org
        request.branch = None
        return None
