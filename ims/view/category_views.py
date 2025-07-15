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
@login_required(login_url='login')
def branch_category(request):
    # Assuming request.user is connected to an organization
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
    return render(request, 'ims/branch_category.html', context)


@role_required(roles=['owner'])
@login_required
def AdminCategory(request, pk):
    organization = request.user.organization
    branch = Branch.objects.get(id=pk, organization=organization)
    category = Category.objects.filter(branch=branch).all()
    paginator = Paginator(category, 15)
    page = request.GET.get('page')
    category_page = paginator.get_page(page)
    nums = "a" * category_page.paginator.num_pages
    category_contains = request.GET.get('category_name')
    form = CategoryForm()
    
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'successfully created')
            return redirect('branch_category')

    if category_contains != '' and category_contains is not None:
        category_page = category.filter(category_name__icontains=category_contains)

    context = {
        'branch': branch,
        'category': category,
        'form': form,
        'category_page': category_page,
        'nums': nums
    }
    return render(request, 'ims/category.html', context)


@role_required(roles=['owner', 'manager'])
@login_required
# @is_unsubscribed
def category_list(request):
    category = Category.objects.all()
    paginator = Paginator(Category.objects.all(), 3)
    page = request.GET.get('page')
    category_page = paginator.get_page(page)
    nums = "a" *category_page.paginator.num_pages
    category_contains = request.GET.get('category_name')
    form = CategoryForm()
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'successfully created')
            return redirect('category_list')
            
    if category_contains != '' and category_contains is not None:
        category_page = category.filter(category_name__icontains=category_contains)

    context = {
        'category':category,
        'form':form,
        'category_page':category_page,
        'nums':nums
    }
    return render(request, 'ims/category.html', context)


@role_required(roles=['owner'])
@login_required
# @is_unsubscribed
def category(request, pk):
    category = Category.objects.get(id=pk)

    context = {
        'category':category
    }
    return render(request, 'modals/edit_category', context)


@role_required(roles=['owner', 'manager'])
def edit_category(request):
    if request.method == 'POST':
        category = Category.objects.get(id = request.POST.get('id'))
        if category != None:
            form = EditCategoryForm(request.POST, instance=category)
            if form.is_valid():
                form.save()
                messages.success(request, 'successfully updated')
                return redirect('category_list')


@role_required(roles=['owner'])
def delete_category(request):
    if request.method == 'POST':
        category = Category.objects.get(id = request.POST.get('id'))
        if category != None:
            category.delete()
            messages.success(request, "Succesfully deleted")
            return redirect('category_list')