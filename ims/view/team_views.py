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
from account.decorators import role_required
from django.template.loader import get_template
from xhtml2pdf import pisa



# Write your views here.

@role_required(roles=['owner'])
@login_required
# @is_unsubscribed
def staffs(request): 
    staff = CustomUser.objects.all()
    paginator = Paginator(CustomUser.objects.all(), 15)
    page = request.GET.get('page')
    staff_page = paginator.get_page(page)
    nums = "a" *staff_page.paginator.num_pages
    staff_contains = request.GET.get('username')
    form = UserCreateForm()
    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, 'Account successfully created for ' + username)

    if staff_contains != '' and staff_contains is not None:
        staff_page = staff.filter(username__icontains=staff_contains)
   
    context = {
        'staff':staff,
        'staff_page':staff_page,
        'nums':nums,
        'form':form
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
    return render(request, 'ims/staff_edit.html', context)


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
# @is_unsubscribed
def record(request):
    login_trail = ActivityLog.objects.all().order_by('-timestamp')
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
        'nums':nums
    }
    return render(request, 'ims/records.html', context)
