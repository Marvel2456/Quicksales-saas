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

@role_required(roles=['owner', 'manager'])
@login_required
# @is_unsubscribed
def product_category(request):
    products = Product.objects.all().order_by('-date_created')
    category = Category.objects.filter().all()
    paginator = Paginator(Product.objects.all(), 15)
    page = request.GET.get('page')
    products_page = paginator.get_page(page)
    nums = "a" *products_page.paginator.num_pages
    product_contains = request.GET.get('product_name')
    form = ProductForm()
    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'successfully created')
            return redirect('products')

    if product_contains != '' and product_contains is not None:
        products_page = products.filter(product_name__icontains=product_contains)
        
    context = {
        'category':category,
        'form':form,
        'products':products,
        'products_page':products_page,
        'nums':nums
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
def edit_product(request):
    if request.method == 'POST':
        product = Product.objects.get(id = request.POST.get('id'))
        if product != None:
            form = EditProductForm(request.POST, instance=product)
            if form.is_valid():
                form.save()
                messages.success(request, 'successfully updated')
                return redirect('products')


@role_required(roles=['owner'])
def delete_product(request):
    if request.method == 'POST':
        product = Product.objects.get(id = request.POST.get('id'))
        if product != None:
            product.delete()
            messages.success(request, "Succesfully deleted")
            return redirect('products')

