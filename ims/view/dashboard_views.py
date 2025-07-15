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
def branchDasboard(request):
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
    return render(request, 'ims/branchdash.html', context)

@login_required(login_url=('login'))
# @is_unsubscribed

def dashboard(request, pk):

    organization = request.user.organization

    branch = Branch.objects.get(id=pk, organization=organization)
    now = datetime.now()
    current_year = now.strftime("%Y")
    current_month = now.strftime("%m")
    current_day = now.strftime("%d")
    products = Product.objects.filter(branch=branch, organization=organization).all()
    category = Category.objects.filter(branch=branch, organization=organization).all()
    
    total_product = products.count()
    total_category = category.count()
    transaction = len(Sale.objects.filter(
        date_added__year=current_year,
        date_added__month = current_month,
        date_added__day = current_day,
        branch_id = pk
    ))
    today_sales = Sale.objects.filter(
        date_added__year=current_year,
        date_added__month = current_month,
        date_added__day = current_day,
        branch_id = pk
    ).all()
    total_sales = sum(today_sales.values_list('final_total_price',flat=True))
    # make graph for highest paid products per day
    today_profit = Sale.objects.filter(
        date_added__year=current_year,
        date_added__month = current_month,
        date_added__day = current_day,
        branch_id = pk
    ).all()
    total_profits = sum(today_profit.values_list('total_profit', flat=True))
    pending = ErrorTicket.objects.filter(status='Pending')
    inventory = Inventory.objects.filter(branch_id = branch).all()

    sale = Sale.objects.filter(branch_id = branch).order_by('-total_profit')[:7]
    item = SalesItem.objects.filter(branch_id = branch).order_by('-quantity')[:7]


    context = {
        'branch':branch,
        'pending':pending,
        'products':products,
        'category':category,
        'total_product':total_product,
        'total_category':total_category,
        'transaction':transaction,
        'total_sales':total_sales,
        'total_profits':total_profits,
        'sale':sale,
        'item':item,
        'inventory':inventory
    }
    return render(request, 'ims/index.html', context)

def staffDashboard(request):
    return render(request, 'ims/dashboard.html')

