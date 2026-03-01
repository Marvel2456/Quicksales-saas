from django.shortcuts import redirect
from django.urls import reverse
from .models import OrganizationMembership


class OrganizationContextMiddleware:
    """
    Middleware to manage the current organization context for multi-org users.
    Stores the active organization ID in the session.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Only process for authenticated users
        if request.user.is_authenticated and not request.user.is_superuser:
            self._set_organization_context(request)
        
        response = self.get_response(request)
        return response
    
    def _set_organization_context(self, request):
        """Set the current organization context for the user"""
        
        # Get active organization from session
        active_org_id = request.session.get('active_organization_id')
        
        # If user has an organization FK (legacy), use it
        if hasattr(request.user, 'organization') and request.user.organization:
            # Backward compatibility: Use the organization FK
            request.organization = request.user.organization
            request.branch = request.user.branch
            request.session['active_organization_id'] = str(request.user.organization.id)
            return
        
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
                request.user.role = membership.role  # Set role for this session
                return
            except OrganizationMembership.DoesNotExist:
                # Invalid org ID in session, clear it
                del request.session['active_organization_id']
        
        # No active org in session, get first available membership
        first_membership = request.user.memberships.select_related(
            'organization', 'branch'
        ).filter(is_active=True).first()
        
        if first_membership:
            request.organization = first_membership.organization
            request.branch = first_membership.branch
            request.user.role = first_membership.role
            request.session['active_organization_id'] = str(first_membership.organization.id)
        else:
            # User has no active memberships
            request.organization = None
            request.branch = None


def switch_organization(request, organization_id):
    """
    Helper function to switch the active organization for a user.
    Call this when user selects a different organization from a dropdown.
    """
    if not request.user.is_authenticated:
        return False
    
    # Verify user has access to this organization
    if request.user.is_member_of_id(organization_id):
        request.session['active_organization_id'] = str(organization_id)
        return True
    
    return False
