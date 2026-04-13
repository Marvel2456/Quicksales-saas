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
from account.utils import get_request_organization
from django.template.loader import get_template
from xhtml2pdf import pisa


# Write your views here.


@role_required(roles=['owner'])
@login_required(login_url='login')
def branch_category(request):
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
    return render(request, 'ims/branch_category.html', context)



@role_required(roles=['owner', 'manager'])
@login_required
# @is_unsubscribed
def category_list(request, pk):
    # Use organization from middleware context (supports multi-org)
    organization = get_request_organization(request)
    branch = Branch.objects.get(organization=organization, id=pk)
    category_qs = Category.objects.filter(branch=branch, organization=organization)
    page = request.GET.get('page')
    category_contains = request.GET.get('category_name')
    form = CategoryForm(organization=organization, branch=branch)
    if request.method == "POST":
        form = CategoryForm(request.POST, organization=organization, branch=branch)
        if form.is_valid():
            category_instance = form.save(commit=False)
            category_instance.branch = branch
            category_instance.organization = organization
            category_instance.save()
            messages.success(request, 'successfully created')
            return redirect('category_list', pk=branch.id)
            
    if category_contains:
        category_qs = category_qs.filter(category_name__icontains=category_contains)

    paginator = Paginator(category_qs, 15)
    category_page = paginator.get_page(page)
    nums = "a" * category_page.paginator.num_pages

    context = {
        'category': category_qs,
        'form': form,
        'category_page': category_page,
        'nums': nums,
        'branch': branch
    }
    return render(request, 'ims/category.html', context)


@role_required(roles=['owner'])
@login_required
# @is_unsubscribed
def category(request, pk):
    organization = get_request_organization(request)
    category = get_object_or_404(Category, id=pk, organization=organization)

    context = {
        'category':category
    }
    return render(request, 'modals/edit_category', context)



@role_required(roles=['owner', 'manager'])
@login_required
def edit_category(request, pk):
    organization = get_request_organization(request)
    category = get_object_or_404(Category, id=pk, organization=organization)

    if request.method == 'POST':
        form = EditCategoryForm(request.POST, instance=category)
        if form.is_valid():
            updated_category = form.save()
            messages.success(request, 'Successfully updated')
            return redirect('category_list', pk=updated_category.branch.id)
    else:
        form = EditCategoryForm(instance=category)

    context = {
        'form': form,
        'category': category,
    }
    return render(request, 'modals/edit_category_modal.html', context)


@role_required(roles=['owner'])
def delete_category(request, pk):
    organization = get_request_organization(request)
    
    if request.method == 'POST':
        category = get_object_or_404(Category, id=pk, organization=organization)
        branch_id = category.branch.id 
        category.delete()
        messages.success(request, "Successfully deleted")
        return redirect('category_list', pk=branch_id)