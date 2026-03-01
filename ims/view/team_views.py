from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.core.mail import send_mail
from django.db import models
from datetime import datetime, date
from ims.models import Category, Product, Sale, SalesItem, Inventory, ErrorTicket
from account.models import CustomUser, Branch, ActivityLog, Notification
from django.contrib.auth.decorators import login_required
from ims.forms import *
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
import csv
import json
import secrets, string
from django.contrib.auth.hashers import make_password
from django.utils.crypto import get_random_string
from account.decorators import role_required, check_user_limit
from account.utils import get_request_organization
from django.template.loader import get_template
from xhtml2pdf import pisa
from account.emails import send_staff_invitation_email
from django.conf import settings
from django.views.decorators.http import require_POST



# Write your views here.
@role_required(roles=['owner'])
@login_required

def branchTeam(request):
    # Use organization from middleware context (supports multi-org)
    organization = get_request_organization(request)
    branch_qs = Branch.objects.filter(organization=organization)

    paginator = Paginator(branch_qs, 15)
    page = request.GET.get('page')
    branch_page = paginator.get_page(page)
    nums = "a" * branch_page.paginator.num_pages

    branch_contains_query = request.GET.get('branch')
    if branch_contains_query:
        branch_page = branch_qs.filter(name__icontains=branch_contains_query)

    context = {
        'branch': branch_qs,
        'branch_page': branch_page,
        'nums': nums
    }
    return render(request, 'ims/branchteam.html', context)


@role_required(roles=['owner'])
@login_required
@check_user_limit
def staffs(request, pk):
    organization = get_request_organization(request)
    branch = Branch.objects.get(organization=organization, id=pk)
    
    # Get staff - check both legacy (organization FK) and new (memberships)
    from account.models import OrganizationMembership
    
    # Get users through active memberships
    # Get users through memberships (both active and inactive) so they show up in the owner's staff list
    membership_user_ids = OrganizationMembership.objects.filter(
        organization=organization,
        branch=branch
    ).values_list('user_id', flat=True)
    
    # Also include legacy users (those with direct organization FK)
    legacy_staff = CustomUser.objects.filter(branch=branch, organization=organization)
    
    # Combine both: users from memberships + legacy users
    staff = CustomUser.objects.filter(
        models.Q(id__in=membership_user_ids) | models.Q(id__in=legacy_staff.values_list('id', flat=True))
    ).distinct()

    paginator = Paginator(staff, 15)
    page = request.GET.get('page')
    staff_page = paginator.get_page(page)
    nums = "a" * staff_page.paginator.num_pages

    form = StaffCreateForm(organization=organization, branch=branch)

    if request.method == 'POST':
        form = StaffCreateForm(request.POST, organization=organization, branch=branch)
        if form.is_valid():
            # Explicitly get email from cleaned_data, must exist if form is valid
            if 'email' not in form.cleaned_data or not form.cleaned_data['email']:
                messages.error(request, "Email is required to add staff.")
                return redirect('staff', pk=branch.id)
            
            email = form.cleaned_data['email'].strip()
            role = form.cleaned_data['role']
            raw_password = None  # Only set for new users
            
            # Check if user already exists in this org
            from account.models import OrganizationMembership
            existing_membership = OrganizationMembership.objects.filter(
                user__email=email,
                organization=organization,
                is_active=True
            ).first()
            
            if existing_membership:
                # User already in this organization
                messages.error(
                    request,
                    f"A staff member with email '{email}' already exists in this organization."
                )
                return redirect('staff', pk=branch.id)
            
            # Try to get existing user (from another organization)
            staff_user, created = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': form.cleaned_data['first_name'],
                    'last_name': form.cleaned_data['last_name'],
                    'phone_number': form.cleaned_data['phone_number'],
                    'role': form.cleaned_data['role'],
                }
            )
            
            # If user was newly created, set password and force change
            if created:
                raw_password = get_random_string(length=12)
                staff_user.set_password(raw_password)
                staff_user.must_change_password = True
                staff_user.organization = organization  # For backward compatibility
                staff_user.branch = branch
                staff_user.save()
            else:
                # For existing users from other orgs, update legacy FK fields for backward compatibility
                # This ensures context resolution works even before session is set
                staff_user.organization = organization
                staff_user.branch = branch
                staff_user.role = role
                staff_user.save()
            
            # Create membership for this organization
            OrganizationMembership.objects.create(
                user=staff_user,
                organization=organization,
                branch=branch,
                role=role,
                is_active=True
            )
            
            # Build login URL
            login_url = f"http://{organization.slug}.{settings.DOMAIN}/account/login/"
            
            if created:
                # New user - send invitation email with password
                try:
                    send_staff_invitation_email(
                        user=staff_user,
                        organization=organization,
                        branch=branch,
                        password=raw_password,
                        login_url=login_url
                    )
                    messages.success(
                        request, 
                        f"Staff account created for {staff_user.get_full_name()} ({staff_user.email}). "
                        f"An invitation email has been sent with login credentials."
                    )
                except Exception as e:
                    messages.warning(
                        request,
                        f"Staff account created but email failed to send. Please provide credentials manually. Error: {str(e)}"
                    )
            else:
                # Existing user - send notification
                try:
                    send_mail(
                        subject=f'Added to {organization.name}',
                        message=f'You have been added to {organization.name} as {role}. Login at {login_url}',
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[staff_user.email],
                        fail_silently=False,
                    )
                    messages.success(
                        request,
                        f"{staff_user.get_full_name()} added to organization."
                    )
                except Exception as e:
                    messages.warning(
                        request,
                        f"User added but email notification failed: {str(e)}"
                    )
            
            # Create notification for owner about new staff member
            if organization.owned_by and organization.owned_by != request.user:
                Notification.objects.create(
                    user=organization.owned_by,
                    message=f"New staff member added: {staff_user.get_full_name() or staff_user.email} ({role}) to {branch.name} branch",
                    notification_type='success',
                    organization=organization,
                    is_read=False
                )
            
            return redirect('staff', pk=branch.id)
            
            return redirect('staff', pk=branch.id)
        else:
            # If form is not valid, add error messages
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            return redirect('staff', pk=branch.id)

    staff_contains = request.GET.get('username')
    if staff_contains:
        staff_page = staff.filter(email__icontains=staff_contains)

    # Enrich staff_page with organization-specific roles and active status
    staff_page_with_roles = []
    for staff_member in staff_page:
        # Try to get org-specific role from membership
        try:
            membership = OrganizationMembership.objects.get(
                user=staff_member,
                organization=organization
            )
            org_role = membership.role
            is_active = membership.is_active
        except OrganizationMembership.DoesNotExist:
            # Fall back to user's global role and active status
            org_role = staff_member.role
            is_active = staff_member.is_active
        
        staff_page_with_roles.append({
            'user': staff_member,
            'org_role': org_role,
            'is_active': is_active
        })

    context = {
        'staff': staff,
        'staff_page': staff_page_with_roles,
        'nums': nums,
        'form': form,
        'branch': branch
    }
    return render(request, 'ims/staff.html', context)


@role_required(roles=['owner'])
@login_required
# @is_unsubscribed
def staff(request, pk):
    staff = CustomUser.objects.get(id=pk)
    form = UserEditForm()

    context = {
        'staff':staff,
        'form':form
    }
    return render(request, 'modals/staff_edit.html', context)


@role_required(roles=['owner'])
@login_required
def edit_staff(request):
    if request.method == 'POST':
        staff_id = request.POST.get('id')
        branch_id = request.POST.get('branch_id')  # Get the branch from hidden input
        try:
            organization = get_request_organization(request)
            staff = CustomUser.objects.get(id=staff_id, organization=organization)
            original_branch = staff.branch  # Save original branch for redirect
            form = UserForm(request.POST, instance=staff)
            if form.is_valid():
                # Don't let the form clear the branch
                staff = form.save(commit=False)
                if not staff.branch:  # If form clears branch, restore it
                    staff.branch_id = branch_id or original_branch.id if original_branch else None
                staff.save()
                messages.success(request, 'Staff member updated successfully')
                # Redirect back to the branch staff list
                if staff.branch:
                    return redirect('staff', pk=staff.branch.id)
                return redirect('branchteam')
            else:
                # Log form errors for debugging
                error_msg = ', '.join([f"{field}: {', '.join(errors)}" for field, errors in form.errors.items()])
                messages.error(request, f'Error updating staff: {error_msg}')
                if original_branch:
                    return redirect('staff', pk=original_branch.id)
                return redirect('branchteam')
        except CustomUser.DoesNotExist:
            messages.error(request, 'Staff member not found')
            return redirect('branchteam')
    
    messages.error(request, 'Invalid request method')
    return redirect('branchteam')




@role_required(roles=['owner'])
@require_POST
def deactivate_staff(request):
    staff = CustomUser.objects.get(id=request.POST.get('id'))
    organization = get_request_organization(request)
    branch = staff.branch
    from account.models import OrganizationMembership
    from django.utils import timezone
    try:
        membership = OrganizationMembership.objects.get(
            user=staff,
            organization=organization
        )
        membership.is_active = False
        membership.date_removed = timezone.now()
        membership.save()
        messages.success(
            request,
            f"{staff.get_full_name() or staff.email}'s account has been deactivated."
        )
    except OrganizationMembership.DoesNotExist:
        # Handle cases where membership doesn't exist yet but user is in org (legacy)
        OrganizationMembership.objects.create(
            user=staff,
            organization=organization,
            branch=branch,
            role=staff.role,
            is_active=False,
            date_removed=timezone.now()
        )
        messages.success(
            request,
            f"{staff.get_full_name() or staff.email}'s account has been deactivated."
        )
    return redirect('staff', pk=branch.id)

@require_POST
def activate_staff(request):
    staff = CustomUser.objects.get(id=request.POST.get('id'))
    organization = get_request_organization(request)
    branch = staff.branch
    from account.models import OrganizationMembership
    try:
        membership = OrganizationMembership.objects.get(
            user=staff,
            organization=organization
        )
        membership.is_active = True
        membership.date_removed = None
        membership.save()
        messages.success(
            request,
            f"{staff.get_full_name() or staff.email}'s account has been activated."
        )
    except OrganizationMembership.DoesNotExist:
        # Handle cases where membership doesn't exist yet but user is in org (legacy)
        OrganizationMembership.objects.create(
            user=staff,
            organization=organization,
            branch=branch,
            role=staff.role,
            is_active=True
        )
        messages.success(
            request,
            f"{staff.get_full_name() or staff.email}'s account has been activated."
        )
    return redirect('staff', pk=branch.id)




@role_required(roles=['owner'])
@login_required
def branchRecord(request):
    # Use organization from middleware context (supports multi-org)
    organization = get_request_organization(request)
    branch_qs = Branch.objects.filter(organization=organization)

    paginator = Paginator(branch_qs, 15)
    page = request.GET.get('page')
    branch_page = paginator.get_page(page)
    nums = "a" * branch_page.paginator.num_pages

    branch_contains_query = request.GET.get('branch')
    if branch_contains_query:
        branch_page = branch_qs.filter(name__icontains=branch_contains_query)

    context = {
        'branch': branch_qs,
        'branch_page': branch_page,
        'nums': nums
    }
    return render(request, 'ims/branchrecord.html', context)



@login_required
# @is_unsubscribed
def record(request, pk):
    organization = get_request_organization(request)
    branch_qs = Branch.objects.filter(organization=organization).order_by('name')
    now = datetime.now()
    start_date_contains = request.GET.get('start_date')
    end_date_contains = request.GET.get('end_date')
    branch_filter = request.GET.get('branch')

    logs = ActivityLog.objects.filter(
        organization=organization,
        activity__icontains='login'
    )

    if branch_filter:
        logs = logs.filter(branch_id=branch_filter)

    if start_date_contains:
        logs = logs.filter(timestamp__date__gte=start_date_contains)
    if end_date_contains:
        logs = logs.filter(timestamp__date__lte=end_date_contains)

    logs = logs.order_by('-timestamp')

    query_params = request.GET.copy()
    query_params.pop('page', None)

    paginator = Paginator(logs, 25)
    page_number = request.GET.get('page')
    logs_page = paginator.get_page(page_number)

    context = {
        'branch': branch_qs.filter(id=branch_filter).first() if branch_filter else None,
        'branches': branch_qs,
        'selected_branch_id': branch_filter,
        'logs_page': logs_page,
        'now':now,
        'start_date': start_date_contains,
        'end_date': end_date_contains,
        'query_params': query_params.urlencode(),
    }
    return render(request, 'ims/record.html', context)
