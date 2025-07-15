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


@role_required(roles=['owner'])
@login_required
# @is_unsubscribed
def branchCount(request):
    branch = Branch.objects.all()

    context = {
        'branch':branch
    }

    return render(request, 'ims/branch_count.html', context)
    
def adminCountView(request, pk):
    branch = Branch.objects.get(id=pk)
    inventory = Inventory.objects.filter(branch_id = pk).all()
    audit = Inventory.history.filter(branch_id = pk).all()

    context = {
        'branch':branch,
        'inventory':inventory,
        'audit':audit
    }
    return render(request, 'ims/admin_count.html', context)


@role_required(roles=['owner', 'manager'])
@login_required
# @is_unsubscribed
def countView(request):
    branch = request.user.branch
    inventory = Inventory.objects.filter(branch_id = branch).all()
    audit = Inventory.history.filter(branch_id = branch).all()

    context = {
        'branch':branch,
        'inventory':inventory,
        'audit':audit
    }
    return render(request, 'ims/count.html', context)


@role_required(roles=['owner', 'manager'])
def addCount(request):
    if request.method == 'POST':
        branch = request.user.branch
        inventory = Inventory.objects.filter(branch_id = branch).get(id = request.POST.get('id'))
        if request.method != None:
            form = AddCountForm(request.POST, instance=inventory)
            if form.is_valid():
                invent = form.save(commit=False)
                invent.variance = inventory.count - inventory.store_quantity
                invent.branch = request.user.branch
                invent.save()
                messages.success(request, 'Count Added Successfully')
                return redirect('count')
    context = {
        'branch':branch
    }

    return HttpResponse(context)




@role_required(roles=['owner'])
@login_required
# @is_unsubscribed
def branchAudit(request):
    branch = Branch.objects.all()

    context = {
        'branch':branch
    }

    return render(request, 'ims/branch_audit.html', context)
