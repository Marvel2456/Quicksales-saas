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
def branchInventory(request):
    inventory = Inventory.objects.all().order_by('branch')
    product = Product.objects.filter().all()
    branch = Branch.objects.filter().all()
    paginator = Paginator(Inventory.objects.all(), 15)
    page = request.GET.get('page')
    inventory_page = paginator.get_page(page)
    nums = "a" *inventory_page.paginator.num_pages
    product_contains_query = request.GET.get('product')
    branch_contains_query = request.GET.get('branch')
    form = AdminCreateInventoryForm
    if request.method == "POST":
        form = AdminCreateInventoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'successfully created')
            return redirect('branchinv')

    if product_contains_query != '' and product_contains_query is not None:
        inventory_page = inventory.filter(product__product_name__icontains=product_contains_query)

    if branch_contains_query != '' and branch_contains_query is not None:
        inventory_page = inventory.filter(branch__branch_name__icontains=branch_contains_query)


    context = {
        'inventory':inventory,
        'product':product,
        'branch':branch,
        'form':form,
        'inventory_page':inventory_page,
        'nums':nums,

    }

    return render(request, 'ims/branch_inv.html', context)



@role_required(roles=['owner', 'manager'])
@login_required
# @is_unsubscribed
def inventory_list(request):
    branch = request.user.branch
    inventory = Inventory.objects.filter(branch_id = branch).all()
    product = Product.objects.filter().all()
    paginator = Paginator(Inventory.objects.filter(branch_id = branch).all(), 15)
    page = request.GET.get('page')
    inventory_page = paginator.get_page(page)
    nums = "a" *inventory_page.paginator.num_pages
    product_contains_query = request.GET.get('product')
    form = CreateInventoryForm
    if request.method == "POST":
        form = CreateInventoryForm(request.POST)
        if form.is_valid():
            invenvt = form.save(commit=False)
            invenvt.branch = request.user.branch
            invenvt.save()
            messages.success(request, 'successfully created')
            return redirect('inventorys')
            # find out why it is redirecting to a wrong url after creating an inventory
    
    if product_contains_query != '' and product_contains_query is not None:
        inventory_page = inventory.filter(product__product_name__icontains=product_contains_query)

    context = {
        'branch':branch,
        'inventory':inventory,
        'product':product,
        'form':form,
        'inventory_page':inventory_page,
        'nums':nums,
    }
    return render(request, 'ims/inventory.html', context)





@role_required(roles=['owner'])
@login_required
# @is_unsubscribed
def branchInventory(request):
    inventory = Inventory.objects.all().order_by('branch')
    product = Product.objects.filter().all()
    branch = Branch.objects.filter().all()
    paginator = Paginator(Inventory.objects.all(), 15)
    page = request.GET.get('page')
    inventory_page = paginator.get_page(page)
    nums = "a" *inventory_page.paginator.num_pages
    product_contains_query = request.GET.get('product')
    branch_contains_query = request.GET.get('branch')
    form = AdminCreateInventoryForm
    if request.method == "POST":
        form = AdminCreateInventoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'successfully created')
            return redirect('branchinv')

    if product_contains_query != '' and product_contains_query is not None:
        inventory_page = inventory.filter(product__product_name__icontains=product_contains_query)

    if branch_contains_query != '' and branch_contains_query is not None:
        inventory_page = inventory.filter(branch__branch_name__icontains=branch_contains_query)


    context = {
        'inventory':inventory,
        'product':product,
        'branch':branch,
        'form':form,
        'inventory_page':inventory_page,
        'nums':nums,

    }

    return render(request, 'ims/branch_inv.html', context)



@role_required(roles=['owner', 'manager'])
@login_required
# @is_unsubscribed
def inventory_list(request):
    branch = request.user.branch
    inventory = Inventory.objects.filter(branch_id = branch).all()
    product = Product.objects.filter().all()
    paginator = Paginator(Inventory.objects.filter(branch_id = branch).all(), 15)
    page = request.GET.get('page')
    inventory_page = paginator.get_page(page)
    nums = "a" *inventory_page.paginator.num_pages
    product_contains_query = request.GET.get('product')
    form = CreateInventoryForm
    if request.method == "POST":
        form = CreateInventoryForm(request.POST)
        if form.is_valid():
            invenvt = form.save(commit=False)
            invenvt.branch = request.user.branch
            invenvt.save()
            messages.success(request, 'successfully created')
            return redirect('inventorys')
            # find out why it is redirecting to a wrong url after creating an inventory
    
    if product_contains_query != '' and product_contains_query is not None:
        inventory_page = inventory.filter(product__product_name__icontains=product_contains_query)

    context = {
        'branch':branch,
        'inventory':inventory,
        'product':product,
        'form':form,
        'inventory_page':inventory_page,
        'nums':nums,
    }
    return render(request, 'ims/inventory.html', context)

# @for_admin
# @login_required
# @is_unsubscribed
# def inventory(request, pk):
#     inventory = Inventory.objects.get(id=pk)

#     context = {
#         'inventory':inventory
#     }
#     return render(request, 'ims/edit_inventory.html', context)


@role_required(roles=['owner'])
def edit_inventory(request, pk):
    branch = Branch.objects.get(id=pk)
    if request.method == 'POST':
        inventory = Inventory.objects.filter().get(id = request.POST.get('id'))
        if inventory != None:
            form = ReorderForm(request.POST, instance=inventory)
            if form.is_valid():
                form.save()
                messages.success(request, 'successfully updated')
                return redirect('inventorys/'+str(branch.id))


def adminRestock(request):
    if request.method == 'POST':
        inventory = Inventory.objects.get(id = request.POST.get('id'))
        if inventory != None:
            form  = AdminRestockForm(request.POST, instance=inventory)
            if form.is_valid():
                form.save(commit=False)
                inventory.quantity += inventory.quantity_restocked
                inventory.save()
                messages.success(request, 'successfully updated')
                return redirect('branchinv')


@role_required(roles=['owner', 'manager'])
def restock(request):
    branch = request.user.branch
    if request.method == 'POST':
        inventory = Inventory.objects.filter(branch_id = branch).get(id = request.POST.get('id'))
        if inventory != None:
            form = RestockForm(request.POST, instance=inventory)
            if form.is_valid():
                invent = form.save(commit=False)
                invent.quantity += invent.quantity_restocked
                invent.branch = request.user.branch
                invent.save()
            
                messages.success(request, 'successfully updated')
                return redirect('inventorys')

    context = {
        'branch':branch
    }
    return HttpResponse(context)


@role_required(roles=['owner', 'manager'])
@login_required
# @is_unsubscribed
def inventoryView(request, pk):
    branch = Branch.objects.get(id=pk)
    inventory = Inventory.objects.filter(branch_id = pk).all()
    product = Product.objects.filter().all()
    paginator = Paginator(Inventory.objects.filter(branch_id = pk).all(), 15)
    page = request.GET.get('page')
    inventory_page = paginator.get_page(page)
    nums = "a" *inventory_page.paginator.num_pages
    product_contains_query = request.GET.get('product')

    if product_contains_query != '' and product_contains_query is not None:
        inventory_page = inventory.filter(product__product_name__icontains=product_contains_query)

    context = {
        'branch':branch,
        'inventory':inventory,
        'product':product,
        'inventory_page':inventory_page,
        'nums':nums,
    }
    return render(request, 'ims/product_list.html', context)


@role_required(roles=['owner'])
def delete_inventory(request, pk):
    branch = Branch.objects.get(id=pk)
    if request.method == 'POST':
        inventory = Inventory.objects.filter(branch_id = pk).get(id = request.POST.get('id'))
        if inventory != None:
            inventory.delete()
            messages.success(request, "Succesfully deleted")
            return redirect('inventorys/'+str(branch.id))
        


@role_required(roles=['owner'])
@login_required
# @is_unsubscribed
def inventoryAudit(request, pk):
    branch = Branch.objects.get(id=pk)
    inventory = Inventory.objects.filter(branch_id = pk).all()
    audit = Inventory.history.filter(branch_id = pk).all()
    paginator = Paginator(Inventory.history.filter(branch_id = pk).all(), 15)
    page = request.GET.get('page')
    audit_page = paginator.get_page(page)
    nums = "a" *audit_page.paginator.num_pages
    product_contains_query = request.GET.get('product')

    if product_contains_query != '' and product_contains_query is not None:
        audit_page = inventory.filter(product__product_name__icontains=product_contains_query)
    context = {
        'branch': branch,
        'inventory':inventory,
        'audit':audit,
        'audit_page':audit_page,
        'nums':nums
    }
    return render(request, 'ims/price_audit.html', context)


@role_required(roles=['owner'])
def export_audit_csv(request, pk):
    branch = Branch.objects.get(id=pk)
    response = HttpResponse(content_type = 'text/csv')
    response['Content-Disposition']='attachment; filename = Audit History'+str(datetime.now())+'.csv'
    writer = csv.writer(response)
    writer.writerow(['Staff', 'Product', 'Date Restocked', 'Quantity Restocked', 'New Cost Price', 'New Sale Price'])
    
    audit = Inventory.history.filter(branch_id = pk).all()
    
    for audit in audit:
        writer.writerow([audit.history_user, audit.product.product_name, audit.history_date, audit.quantity_restocked, audit.cost_price, audit.sale_price])
    
    return response
