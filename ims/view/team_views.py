from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect
from django.contrib import messages
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
from django.template.loader import get_template
from xhtml2pdf import pisa
from account.emails import send_staff_invitation_email
from django.conf import settings



# Write your views here.
@role_required(roles=['owner'])
@login_required
def branchTeam(request):
    organization = request.user.organization
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
    organization = request.user.organization
    branch = Branch.objects.get(organization=organization, id=pk)
    staff = CustomUser.objects.filter(branch=branch)

    paginator = Paginator(staff, 15)
    page = request.GET.get('page')
    staff_page = paginator.get_page(page)
    nums = "a" * staff_page.paginator.num_pages

    form = StaffCreateForm()

    if request.method == 'POST':
        form = StaffCreateForm(request.POST)
        if form.is_valid():
            # Check if email already exists in this organization
            email = form.cleaned_data.get('email')
            if CustomUser.objects.filter(organization=organization, email=email).exists():
                messages.error(
                    request,
                    f"A staff member with email '{email}' already exists in this organization."
                )
                return redirect('staff', pk=branch.id)
            
            staff_user = form.save(commit=False)
            staff_user.organization = organization
            staff_user.branch = branch
            staff_user.role = form.cleaned_data['role']

            # Generate random password
            raw_password = get_random_string(length=12)
            staff_user.set_password(raw_password)
            # Force password change on first login
            staff_user.must_change_password = True
            staff_user.save()

            # Build login URL
            login_url = f"http://{organization.slug}.{settings.DOMAIN}/account/login/"

            # Send invitation email with password and login link
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

            # Create notification for owner about new staff member
            if organization.owned_by and organization.owned_by != request.user:
                Notification.objects.create(
                    user=organization.owned_by,
                    message=f"New staff member added: {staff_user.get_full_name() or staff_user.email} ({staff_user.role}) to {branch.name} branch",
                    notification_type='success',
                    is_read=False
                )
            
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

    context = {
        'staff': staff,
        'staff_page': staff_page,
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
            staff = CustomUser.objects.get(id=staff_id, organization=request.user.organization)
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
def delete_staff(request):
    if request.method == 'POST':
        staff = CustomUser.objects.get(id=request.POST.get('id'))
        branch = staff.branch
        if staff != None:
            staff.delete()
            messages.success(request, "Staff member successfully deleted")
            return redirect('staff', pk=branch.id)




@role_required(roles=['owner'])
@login_required
def branchRecord(request):
    organization = request.user.organization
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
    organization = request.user.organization
    branch = get_object_or_404(Branch, id=pk, organization=organization)
    now = datetime.now()
    start_date_contains = request.GET.get('start_date')
    end_date_contains = request.GET.get('end_date')
    logs = ActivityLog.objects.filter(branch=branch, organization=organization, activity__icontains='login')

    if start_date_contains:
        logs = logs.filter(timestamp__date__gte=start_date_contains)
    if end_date_contains:
        logs = logs.filter(timestamp__date__lte=end_date_contains)

    logs = logs.order_by('-timestamp')

    paginator = Paginator(logs, 25)
    page_number = request.GET.get('page')
    logs_page = paginator.get_page(page_number)

    context = {
        'branch':branch,
        'logs_page': logs_page,
        'now':now,
        'start_date': start_date_contains,
        'end_date': end_date_contains,
    }
    return render(request, 'ims/record.html', context)
