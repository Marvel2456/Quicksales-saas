from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect
from django.contrib import messages
from datetime import datetime, date
from ims.models import Category, Product, Sale, SalesItem, Inventory, ErrorTicket
from account.models import CustomUser, Branch, ActivityLog
from django.contrib.auth.decorators import login_required
from ims.forms import *
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
import csv
import json
import secrets, string
from django.contrib.auth.hashers import make_password
from django.utils.crypto import get_random_string
from account.decorators import role_required
from django.template.loader import get_template
from xhtml2pdf import pisa
from account.emails import send_staff_welcome_email



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
            staff_user = form.save(commit=False)
            staff_user.organization = organization
            staff_user.branch = branch
            staff_user.role = form.cleaned_data['role']

            # Generate random password
            raw_password = get_random_string(length=8)
            staff_user.set_password(raw_password)
            staff_user.save()

            # Send welcome email with password and login link
            send_staff_welcome_email(staff_user, raw_password)

            messages.success(request, f"Staff account created for {staff_user.get_full_name()} ({staff_user.email})")
            return redirect('staff', pk=branch.id)

    staff_contains = request.GET.get('username')
    if staff_contains:
        staff_page = staff.filter(email__icontains=staff_contains)

    context = {
        'staff': staff,
        'staff_page': staff_page,
        'nums': nums,
        'form': form
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
# @is_unsubscribed
def edit_staff(request):
    if request.method == 'POST':
        staff = CustomUser.objects.get(id=request.POST.get('id'))
        if staff != None:
            form = UserForm(request.POST, instance=staff)
            if form.is_valid():
                form.save()
                messages.success(request, 'successfully updated')
                return redirect('staff')



@role_required(roles=['owner'])
def delete_staff(request):
    if request.method == 'POST':
        staff = CustomUser.objects.get(id = request.POST.get('id')) 
        if staff != None:
            staff.delete()
            messages.success(request, "Succesfully deleted")
            return redirect('staff')




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




@role_required(roles=['owner'])
@login_required
# @is_unsubscribed
def record(request, pk):
    organization = request.user.organization
    branch = Branch.objects.get(organization=organization, id=pk)
    login_trail = ActivityLog.objects.filter(branch=branch).order_by('-timestamp')
    paginator = Paginator(ActivityLog.objects.all(), 15)
    page = request.GET.get('page')
    login_trail_page = paginator.get_page(page)
    nums = "a" *login_trail_page.paginator.num_pages
    staff_contains = request.GET.get('staff')

    if staff_contains != '' and staff_contains is not None:
        login_trail_page = login_trail.filter(staff__icontains=staff_contains)

    context = {
        'login_trail':login_trail,
        'login_trail_page':login_trail_page,
        'branch':branch,
        'nums':nums
    }
    return render(request, 'ims/records.html', context)
