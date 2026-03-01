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
from account.utils import get_request_organization, get_request_branch
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.db.models import Sum, Count, Q
from collections import defaultdict
import calendar
from ims.view_caching import cached_view

# Write your views here.


# @cached_view(timeout=120, key_prefix='branch_dashboard')
@role_required(roles=['owner'])
@login_required(login_url='login')
def branchDasboard(request):
    # Use organization from middleware context (supports multi-org)
    organization = get_request_organization(request)
    
    now = datetime.now()
    current_year = now.strftime("%Y")
    current_month = now.strftime("%m")
    current_day = now.strftime("%d")

    # Optimized query: use only necessary fields and filter at database level
    branch_qs = Branch.objects.filter(organization=organization)

    # Calculate today's sales for each branch
    branch_sales_data = []
    for branch in branch_qs:
        # Use aggregate to avoid loading individual objects
        sales_agg = Sale.objects.filter(
            branch=branch,
            date_added__year=current_year,
            date_added__month=current_month,
            date_added__day=current_day
        ).aggregate(
            total_sales=Sum('final_total_price'),
            transaction_count=Count('id')
        )
        
        branch_sales_data.append({
            'branch': branch,
            'today_sales': sales_agg['total_sales'] or 0,
            'transaction_count': sales_agg['transaction_count'] or 0
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

# @cached_view(timeout=120, key_prefix='dashboard')
@login_required(login_url=('login'))
# @is_unsubscribed

def dashboard(request, pk):

    # Use organization from middleware context (supports multi-org)
    organization = get_request_organization(request)

    try:
        branch = Branch.objects.get(id=pk, organization=organization)
    except Branch.DoesNotExist:
        # Branch doesn't belong to current organization
        # Redirect to user's actual branch
        user_branch = get_request_branch(request)
        if user_branch:
            messages.warning(
                request,
                "You don't have access to that branch. Redirecting to your branch."
            )
            return redirect('branchdash', pk=user_branch.id)
        else:
            messages.error(request, "No branch assigned to your account.")
            return redirect('account')
    
    # Store current branch in session for sidebar navigation
    request.session['active_branch_id'] = str(pk)
    request.session['active_branch_name'] = branch.name
    request.session.modified = True
    
    now = datetime.now()
    current_year = now.strftime("%Y")
    current_month = now.strftime("%m")
    current_day = now.strftime("%d")
    
    # Optimized queries: use count() instead of .all() for simple counts
    products = Product.objects.filter(branch=branch, organization=organization)
    category = Category.objects.filter(branch=branch, organization=organization)
    
    total_product = products.count()
    total_category = category.count()
    
    # Use aggregate for sum/count to avoid loading all objects
    today_sales_agg = Sale.objects.filter(
        date_added__year=current_year,
        date_added__month=current_month,
        date_added__day=current_day,
        branch_id=pk
    ).aggregate(
        count=Count('id'),
        total_sales=Sum('final_total_price'),
        total_profit=Sum('total_profit')
    )
    
    transaction = today_sales_agg['count'] or 0
    total_sales = today_sales_agg['total_sales'] or 0
    total_profits = today_sales_agg['total_profit'] or 0
    
    pending = ErrorTicket.objects.filter(status='Pending').count()
    inventory = Inventory.objects.filter(branch_id=branch)

    # Top 7 recent high-quantity sales for bar chart (optimized with select_related)
    item = SalesItem.objects.filter(branch_id=branch).select_related(
        'inventory__product'
    ).order_by('-quantity')[:7]

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
    
    # Get monthly profit data for the current year (for comparison chart)
    monthly_profits = defaultdict(float)
    profits_by_month = (
        Sale.objects.filter(
            branch_id=branch,
            date_added__year=current_year
        )
        .values('date_added__month')
        .annotate(total_profit=Sum('total_profit'))
        .order_by('date_added__month')
    )
    
    for profit in profits_by_month:
        month_num = profit['date_added__month']
        monthly_profits[month_num] = profit['total_profit']
    
    # Create profit values for all 12 months
    month_profit_values = [monthly_profits.get(i, 0) for i in range(1, 13)]
    
    # Calculate daily sales data for the current month (for area chart)
    daily_sales = defaultdict(float)
    daily_profits = defaultdict(float)
    
    daily_stats = (
        Sale.objects.filter(
            branch_id=branch,
            date_added__year=current_year,
            date_added__month=int(current_month)
        )
        .values('date_added__day')
        .annotate(daily_revenue=Sum('final_total_price'), daily_profit=Sum('total_profit'))
        .order_by('date_added__day')
    )
    
    for stat in daily_stats:
        day = stat['date_added__day']
        daily_sales[day] = stat['daily_revenue'] or 0
        daily_profits[day] = stat['daily_profit'] or 0
    
    # Get the number of days in current month
    num_days = calendar.monthrange(int(current_year), int(current_month))[1]
    daily_labels = [str(i) for i in range(1, num_days + 1)]
    daily_revenue_values = [daily_sales.get(i, 0) for i in range(1, num_days + 1)]
    daily_profit_values = [daily_profits.get(i, 0) for i in range(1, num_days + 1)]

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
        'month_profit_values': month_profit_values,
        'daily_labels': daily_labels,
        'daily_revenue_values': daily_revenue_values,
        'daily_profit_values': daily_profit_values,
        'current_month_name': calendar.month_name[int(current_month)],
    }
    return render(request, 'ims/index.html', context)

def staffDashboard(request):
    return render(request, 'ims/dashboard.html')

