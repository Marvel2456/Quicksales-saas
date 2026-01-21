from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect
from django.contrib import messages
from datetime import datetime, date, timedelta
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
from django.db.models import Sum, Count, Q
from collections import defaultdict
import calendar

# Write your views here.


@role_required(roles=['owner'])
@login_required(login_url='login')
def branchDasboard(request):
    # Assuming request.user is connected to an organization
    organization = request.user.organization
    now = datetime.now()
    current_year = now.strftime("%Y")
    current_month = now.strftime("%m")
    current_day = now.strftime("%d")

    branch_qs = Branch.objects.filter(organization=organization)

    # Calculate today's sales for each branch
    branch_sales_data = []
    for branch in branch_qs:
        today_sales = Sale.objects.filter(
            branch=branch,
            date_added__year=current_year,
            date_added__month=current_month,
            date_added__day=current_day
        )
        total_sales = sum(today_sales.values_list('final_total_price', flat=True)) or 0
        transaction_count = today_sales.count()
        
        branch_sales_data.append({
            'branch': branch,
            'today_sales': total_sales,
            'transaction_count': transaction_count
        })

    paginator = Paginator(branch_sales_data, 15)
    page = request.GET.get('page')
    branch_page = paginator.get_page(page)
    nums = "a" * branch_page.paginator.num_pages

    branch_contains_query = request.GET.get('branch')
    if branch_contains_query:
        branch_sales_data = [
            item for item in branch_sales_data 
            if branch_contains_query.lower() in item['branch'].name.lower()
        ]
        branch_page = branch_sales_data

    context = {
        'branch': branch_qs,
        'branch_page': branch_page,
        'nums': nums,
        'organization': organization
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

    # Top 7 recent high-quantity sales for bar chart
    item = SalesItem.objects.filter(branch_id = branch).order_by('-quantity')[:7]

    # Get top 5 selling products by total quantity sold for pie chart
    top_products = (
        SalesItem.objects.filter(branch_id=branch)
        .values('inventory__product__product_name')
        .annotate(total_quantity=Sum('quantity'))
        .order_by('-total_quantity')[:5]
    )

    # Get monthly sales data for the current year (line chart)
    monthly_sales = defaultdict(float)
    sales_by_month = (
        Sale.objects.filter(
            branch_id=branch,
            date_added__year=current_year
        )
        .values('date_added__month')
        .annotate(total_sales=Sum('final_total_price'))
        .order_by('date_added__month')
    )
    
    for sale in sales_by_month:
        month_num = sale['date_added__month']
        monthly_sales[month_num] = sale['total_sales']
    
    # Create lists for all 12 months with data or 0
    month_labels = [calendar.month_abbr[i] for i in range(1, 13)]
    month_values = [monthly_sales.get(i, 0) for i in range(1, 13)]

    context = {
        'branch':branch,
        'organization': organization,
        'pending':pending,
        'products':products,
        'category':category,
        'total_product':total_product,
        'total_category':total_category,
        'transaction':transaction,
        'total_sales':total_sales,
        'total_profits':total_profits,
        'item':item,
        'inventory':inventory,
        'top_products': top_products,
        'month_labels': month_labels,
        'month_values': month_values,
    }
    return render(request, 'ims/index.html', context)

def staffDashboard(request):
    return render(request, 'ims/dashboard.html')

