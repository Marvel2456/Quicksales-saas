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
def branch_product(request):
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
    return render(request, 'ims/branch_product.html', context)

@role_required(roles=['owner', 'manager'])
@login_required
# @is_unsubscribed
def product_category(request, pk):
    organization = request.user.organization
    branch = Branch.objects.get(organization=organization, id=pk)
    product = Product.objects.filter(branch=branch).all().order_by('-created_at')
    category = Category.objects.filter(branch=branch).all()
    paginator = Paginator(Product.objects.all(), 15)
    page = request.GET.get('page')
    products_page = paginator.get_page(page)
    nums = "a" *products_page.paginator.num_pages
    product_contains = request.GET.get('product_name')
    form = ProductForm()
    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            product_instance = form.save(commit=False)
            product_instance.branch = branch
            product_instance.organization = organization
            product_instance.save()
            messages.success(request, 'successfully created')
            return redirect('products', pk=branch.id)

    if product_contains != '' and product_contains is not None:
        products_page = product.filter(product_name__icontains=product_contains)
        
    context = {
        'category':category,
        'form':form,
        'product':product,
        'products_page':products_page,
        'nums':nums,
        'branch':branch
    }
    return render(request, 'ims/products.html', context)


@role_required(roles=['owner'])
def product(request, pk):
    products = Product.objects.get(id=pk)

    context = {
        'products':products
    } 
    return render(request, 'modals/modal_edit_product.html', context)


@role_required(roles=['owner'])
def edit_product(request, pk):
    organization = request.user.organization
    product = get_object_or_404(Product, id=pk, organization=organization)

    if request.method == 'POST':
        form = EditProductForm(request.POST, instance=product)
        if form.is_valid():
            updated_product = form.save()
            messages.success(request, 'Successfully updated')
            return redirect('products', pk=updated_product.branch.id)
    else:
        form = EditProductForm(instance=product)

    # ✅ Pass all categories for the <select>
    categories = Category.objects.filter(organization=organization)

    context = {
        'form': form,
        'product': product,
        'categories': categories,  # ✅ this is what your modal uses
    }
    return render(request, 'modals/modal_edit_product.html', context)



@role_required(roles=['owner'])
def delete_product(request):
    if request.method == 'POST':
        product = Product.objects.get(id = request.POST.get('id'))
        if product != None:
            product.delete()
            messages.success(request, "Succesfully deleted")
            return redirect('products')

