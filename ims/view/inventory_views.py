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



@role_required(roles=['owner'])
@login_required
def branch_inventory(request):
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
    return render(request, 'ims/branch_inv.html', context)



@role_required(roles=['owner', 'manager'])
@login_required
# @is_unsubscribed
def inventory_list(request, pk):
    organization = request.user.organization
    branch = Branch.objects.get(organization=organization, id=pk)
    inventory = Inventory.objects.filter(branch=branch).all().order_by('-last_updated')
    product = Product.objects.filter(branch=branch).all()
    paginator = Paginator(Inventory.objects.filter(branch=branch).all(), 15)
    page = request.GET.get('page')
    inventory_page = paginator.get_page(page)
    nums = "a" *inventory_page.paginator.num_pages
    product_contains_query = request.GET.get('product')
    form = CreateInventoryForm
    if request.method == "POST":
        form = CreateInventoryForm(request.POST)
        if form.is_valid():
            invenvtory_instance = form.save(commit=False)
            invenvtory_instance.branch = branch
            invenvtory_instance.organization = organization
            invenvtory_instance.status = 'Available'
            invenvtory_instance.save()
            messages.success(request, 'successfully created')
            return redirect('inventorys', pk=branch.id)
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



@role_required(roles=['owner'])
def inventory(request, pk):
    inventory = Inventory.objects.get(id=pk)

    context = {
        'inventory':inventory
    }
    return render(request, 'modals/set_reoder.html', context)


@role_required(roles=['owner', 'manager'])
def edit_inventory(request, pk):
    organization = request.user.organization
    if request.method == 'POST':
        inventory = get_object_or_404(Inventory, id=pk, organization=organization)
        if inventory != None:
            form = ReorderForm(request.POST, instance=inventory)
            if form.is_valid():
                form.save()
                messages.success(request, 'successfully updated')
                return redirect('inventorys', pk=inventory.branch.id)
            
    else:
        form = ReorderForm(instance=inventory)

    context = {
        'form': form,
        'inventory': inventory,
    }
    return render(request, context)


# def adminRestock(request):
#     if request.method == 'POST':
#         inventory = Inventory.objects.get(id = request.POST.get('id'))
#         if inventory != None:
#             form  = AdminRestockForm(request.POST, instance=inventory)
#             if form.is_valid():
#                 form.save(commit=False)
#                 inventory.quantity += inventory.quantity_restocked
#                 inventory.save()
#                 messages.success(request, 'successfully updated')
#                 return redirect('branchinv')

# @role_required(roles=['owner'])
# def edit_product(request, pk):
#     organization = request.user.organization
#     product = get_object_or_404(Product, id=pk, organization=organization)

#     if request.method == 'POST':
#         form = EditProductForm(request.POST, instance=product)
#         if form.is_valid():
#             updated_product = form.save()
#             messages.success(request, 'Successfully updated')
#             return redirect('products', pk=updated_product.branch.id)
#     else:
#         form = EditProductForm(instance=product)

#     categories = Category.objects.filter(organization=organization)

#     context = {
#         'form': form,
#         'product': product,
#         'categories': categories,
#     }
#     return render(request, context)



@role_required(roles=['owner', 'manager'])
def restock(request, pk):
    organization = request.user.organization
    inventory = get_object_or_404(Inventory, id=pk, organization=organization)
    if request.method == 'POST':
        form = RestockForm(request.POST, instance=inventory)
        if form.is_valid():
            restocked_inventory = form.save(commit=False)
            restocked_inventory.quantity += restocked_inventory.quantity_restocked
            restocked_inventory.quantity_restocked = restocked_inventory.quantity_restocked or 0
            restocked_inventory.save()
            # Reset quantity_restocked to zero so future non-restock saves (e.g., sales) don't carry old restock values into history
            Inventory.objects.filter(id=restocked_inventory.id).update(quantity_restocked=0)
            messages.success(request, 'Successfully updated')
            return redirect('inventorys', pk=restocked_inventory.branch.id)
    else:
        form = RestockForm(instance=inventory)

    context = {
        'form': form,
        'inventory': inventory,
        'branch': inventory.branch,
    }
    return render(request, 'modals/restock.html', context)


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
        


