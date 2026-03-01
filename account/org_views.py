"""Views for organization switching and management"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.conf import settings
from .models import Organization, OrganizationMembership
from .emails import get_protocol


@login_required(login_url='login')
def user_organizations(request):
    """API endpoint to get user's organizations with login URLs"""
    user = request.user
    
    # Get all active memberships for the user
    memberships = user.memberships.filter(is_active=True).select_related('organization', 'branch')
    
    organizations = []
    for membership in memberships:
        org = membership.organization
        protocol = get_protocol()
        login_url = f"{protocol}://{org.slug}.{settings.DOMAIN}/account/login/"
        
        organizations.append({
            'id': str(org.id),
            'name': org.name,
            'slug': org.slug,
            'logo_url': org.logo.url if org.logo else None,
            'login_url': login_url,
            'role': membership.role,
            'branch_name': membership.branch.name if membership.branch else None,
            'is_current': str(org.id) == str(request.session.get('active_organization_id')),
        })
    
    return JsonResponse({
        'count': len(organizations),
        'organizations': organizations
    })


@login_required(login_url='login')
def switch_organization(request, org_id):
    """Switch the current active organization for the user"""
    user = request.user
    
    try:
        # Verify user has access to this organization
        membership = user.memberships.get(
            organization_id=org_id,
            is_active=True
        )
        
        # Update session to track active organization
        request.session['active_organization_id'] = org_id
        request.session['active_branch_id'] = str(membership.branch.id) if membership.branch else None
        request.session.modified = True
        
        # Get the organization's slug for redirect
        org = membership.organization
        protocol = get_protocol()
        
        # Determine where to redirect based on user role
        redirect_url = f"{protocol}://{org.slug}.{settings.DOMAIN}/account/dashboard/"
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # AJAX request - return JSON
            return JsonResponse({
                'success': True,
                'organization_name': org.name,
                'redirect_url': redirect_url
            })
        else:
            # Regular request - redirect to dashboard
            return redirect(redirect_url)
    
    except OrganizationMembership.DoesNotExist:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'You do not have access to this organization'
            }, status=403)
        else:
            return HttpResponse('Unauthorized', status=403)


@login_required(login_url='login')
def select_organization(request):
    """Page to select organization after login if user has multiple orgs"""
    user = request.user
    
    # Get all active memberships for the user
    memberships = user.memberships.filter(is_active=True).select_related('organization', 'branch')
    
    if memberships.count() == 0:
        return HttpResponse('You do not have access to any organizations', status=403)
    
    if memberships.count() == 1:
        # Only one organization - set it and redirect
        membership = memberships.first()
        request.session['active_organization_id'] = str(membership.organization.id)
        request.session['active_branch_id'] = str(membership.branch.id) if membership.branch else None
        request.session.modified = True
        
        org = membership.organization
        protocol = get_protocol()
        return redirect(f"{protocol}://{org.slug}.{settings.DOMAIN}/account/login/")
    
    # Multiple organizations - show selection page
    organizations = []
    protocol = get_protocol()
    
    for membership in memberships:
        org = membership.organization
        login_url = f"{protocol}://{org.slug}.{settings.DOMAIN}/"
        
        organizations.append({
            'id': str(org.id),
            'name': org.name,
            'slug': org.slug,
            'logo_url': org.logo.url if org.logo else None,
            'role': membership.role,
            'branch_name': membership.branch.name if membership.branch else None,
            'login_url': login_url,
        })
    
    return render(request, 'account/select_organization.html', {
        'organizations': organizations,
        'user': user
    })
