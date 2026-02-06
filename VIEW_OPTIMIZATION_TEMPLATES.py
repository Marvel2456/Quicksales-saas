"""
View Optimization Templates & Examples
Copy these templates into your views to implement the patterns consistently.
"""

# ============================================================================
# TEMPLATE 1: Basic View Optimization Pattern
# ============================================================================

"""
Use this template for any list/detail view optimization
"""

# BEFORE - Unoptimized
from django.shortcuts import render
from ims.models import Sale

def sales_list_old(request):
    sales = Sale.objects.all()  # Loads all sales
    total = sum(s.final_total_price for s in sales)  # Python calculation
    transaction_count = len(sales)  # Loads all to count
    
    context = {
        'sales': sales,
        'total': total,
        'count': transaction_count,
    }
    return render(request, 'sales_list.html', context)


# AFTER - Optimized
from django.shortcuts import render
from django.db.models import Sum, Count
from ims.models import Sale
from account.models import Branch, Organization

def sales_list_new(request):
    # Filter to specific organization
    sales_qs = Sale.objects.filter(
        organization=request.user.organization
    ).select_related(
        'branch',  # ForeignKey
        'staff'    # ForeignKey
    ).prefetch_related(
        'salesitem_set'  # Reverse FK for SalesItem
    )
    
    # Use aggregate for calculations (database-level)
    stats = sales_qs.aggregate(
        total=Sum('final_total_price'),
        count=Count('id')
    )
    
    context = {
        'sales': sales_qs[:50],  # Paginate
        'total': stats['total'] or 0,
        'count': stats['count'] or 0,
    }
    return render(request, 'sales_list.html', context)


# ============================================================================
# TEMPLATE 2: Dashboard View with Caching
# ============================================================================

from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from django.views import View
from django.db.models import Sum, Count, Q
from ims.models import Sale, Inventory, Category
from ims.cache_utils import get_cached_org_dashboard, cache_org_dashboard
from ImsV3.settings import CACHE_TIMEOUTS

# Option A: Function-based view with caching
@cache_page(CACHE_TIMEOUTS['dashboard'])
def dashboard_cached(request, branch_id):
    org = request.user.organization
    branch = Branch.objects.get(id=branch_id, organization=org)
    
    # All queries use aggregate/count instead of Python loops
    stats = Sale.objects.filter(
        organization=org,
        branch=branch,
        date_added__date=timezone.now().date()
    ).aggregate(
        total_sales=Sum('final_total_price'),
        total_profit=Sum('total_profit'),
        transaction_count=Count('id')
    )
    
    low_stock = Inventory.objects.filter(
        organization=org,
        branch=branch,
        quantity__lt=F('reorder_level')  # Compare with field
    ).count()
    
    context = {
        'branch': branch,
        'total_sales': stats['total_sales'] or 0,
        'total_profit': stats['total_profit'] or 0,
        'transactions': stats['transaction_count'] or 0,
        'low_stock_count': low_stock,
    }
    return render(request, 'dashboard.html', context)


# Option B: Class-based view with manual caching
from django.views import View
from django.utils import timezone

class DashboardView(View):
    def get(self, request, branch_id):
        org = request.user.organization
        
        # Check cache first
        cache_key = f'dashboard:org:{org.id}:branch:{branch_id}'
        cached_data = get_cached_org_dashboard(org.id, branch_id)
        
        if cached_data:
            return render(request, 'dashboard.html', cached_data)
        
        # Calculate fresh data
        branch = Branch.objects.get(id=branch_id, organization=org)
        
        stats = Sale.objects.filter(
            organization=org,
            branch=branch,
            date_added__date=timezone.now().date()
        ).aggregate(
            total_sales=Sum('final_total_price'),
            total_profit=Sum('total_profit'),
            transaction_count=Count('id')
        )
        
        context = {
            'branch': branch,
            'total_sales': stats['total_sales'] or 0,
            'total_profit': stats['total_profit'] or 0,
            'transactions': stats['transaction_count'] or 0,
        }
        
        # Cache for next request
        cache_org_dashboard(org.id, branch_id, context)
        
        return render(request, 'dashboard.html', context)


# ============================================================================
# TEMPLATE 3: List View with Pagination & Optimization
# ============================================================================

from django.core.paginator import Paginator
from django.db.models import Sum, Count, F

def sales_report(request):
    org = request.user.organization
    branch = request.GET.get('branch')
    page = request.GET.get('page', 1)
    
    # Start with base optimized queryset
    sales_qs = Sale.objects.filter(
        organization=org
    ).select_related(
        'branch',
        'staff'
    ).order_by('-date_added')
    
    # Apply filters
    if branch:
        sales_qs = sales_qs.filter(branch_id=branch)
    
    # Paginate
    paginator = Paginator(sales_qs, 50)  # 50 per page
    sales_page = paginator.get_page(page)
    
    # Get aggregate stats for the page
    page_stats = sales_qs.filter(
        id__in=[s.id for s in sales_page]
    ).aggregate(
        total_sales=Sum('final_total_price'),
        total_profit=Sum('total_profit')
    )
    
    context = {
        'sales': sales_page,
        'page_total_sales': page_stats['total_sales'] or 0,
        'page_total_profit': page_stats['total_profit'] or 0,
        'paginator': paginator,
    }
    return render(request, 'sales_report.html', context)


# ============================================================================
# TEMPLATE 4: Prefetch_related for Reverse Relations
# ============================================================================

from django.db.models import Prefetch

def organization_detail(request, org_id):
    # Get organization with all related data in one query
    org = Organization.objects.prefetch_related(
        'branch_set',          # Reverse FK: Branch.organization
        'customuser_set',      # Reverse FK: CustomUser.organization
        'activitylog_set',     # Reverse FK: ActivityLog.organization
        Prefetch(
            'branch_set',
            Branch.objects.prefetch_related(
                'inventory_set'
            )
        )
    ).get(id=org_id)
    
    # Access relations without extra queries
    branches = org.branch_set.all()
    users = org.customuser_set.all()
    
    # Each branch already has inventory_set prefetched
    for branch in branches:
        inventory = branch.inventory_set.all()  # No query!
    
    context = {
        'organization': org,
        'branches': branches,
        'users': users,
    }
    return render(request, 'org_detail.html', context)


# ============================================================================
# TEMPLATE 5: Complex Aggregate Queries
# ============================================================================

from django.db.models import Sum, Count, Avg, Q, F
from datetime import timedelta
from django.utils import timezone

def sales_analytics(request):
    org = request.user.organization
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    
    # Single query with multiple aggregates
    analytics = Sale.objects.filter(
        organization=org,
        date_added__date__gte=week_ago
    ).aggregate(
        # By date
        today_sales=Sum(
            'final_total_price',
            filter=Q(date_added__date=today)
        ),
        week_sales=Sum(
            'final_total_price',
            filter=Q(date_added__date__gte=week_ago)
        ),
        
        # Counts
        today_transactions=Count(
            'id',
            filter=Q(date_added__date=today)
        ),
        week_transactions=Count(
            'id',
            filter=Q(date_added__date__gte=week_ago)
        ),
        
        # By status
        completed_sales=Sum(
            'final_total_price',
            filter=Q(completed=True)
        ),
        pending_sales=Sum(
            'final_total_price',
            filter=Q(completed=False)
        ),
        
        # Averages
        avg_transaction_value=Avg('final_total_price'),
    )
    
    context = {
        'today_sales': analytics['today_sales'] or 0,
        'week_sales': analytics['week_sales'] or 0,
        'avg_transaction': analytics['avg_transaction_value'] or 0,
    }
    return JsonResponse(context)


# ============================================================================
# TEMPLATE 6: Signal-Based Cache Invalidation
# ============================================================================

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from ims.cache_utils import (
    invalidate_org_dashboard,
    invalidate_sales_list,
    invalidate_inventory_list
)

@receiver(post_save, sender=Sale)
def invalidate_on_sale_created(sender, instance, created, **kwargs):
    """Invalidate caches when a sale is created/updated"""
    if created:
        # Invalidate dashboards
        invalidate_org_dashboard(instance.organization_id, instance.branch_id)
        # Invalidate sales lists
        invalidate_sales_list(instance.organization_id, instance.branch_id)

@receiver(post_save, sender=Inventory)
def invalidate_on_inventory_updated(sender, instance, **kwargs):
    """Invalidate inventory cache when items are updated"""
    invalidate_inventory_list(instance.organization_id, instance.branch_id)

@receiver(post_delete, sender=SalesItem)
def invalidate_on_sales_item_deleted(sender, instance, **kwargs):
    """Clear caches when sales items are removed"""
    # Cascade invalidation
    invalidate_org_dashboard(instance.organization_id, instance.branch_id)
    invalidate_sales_list(instance.organization_id, instance.branch_id)
    invalidate_inventory_list(instance.organization_id, instance.branch_id)

# Register signals in apps.py
# from django.apps import AppConfig
# class ImsConfig(AppConfig):
#     default_auto_field = 'django.db.models.BigAutoField'
#     name = 'ims'
#     
#     def ready(self):
#         import ims.signals  # Import signals when app is ready


# ============================================================================
# TEMPLATE 7: API View Optimization (Django REST Framework)
# ============================================================================

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import viewsets
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

class SalesPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'

class SalesViewSet(viewsets.ModelViewSet):
    serializer_class = SalesSerializer
    pagination_class = SalesPagination
    
    def get_queryset(self):
        """Optimized queryset with select/prefetch_related"""
        return Sale.objects.filter(
            organization=self.request.user.organization
        ).select_related(
            'branch',
            'staff'
        ).prefetch_related(
            'salesitem_set__inventory__product'
        ).order_by('-date_added')

@method_decorator(cache_page(120), name='dispatch')  # Cache API responses
class SalesMetricsAPIView(APIView):
    def get(self, request):
        org = request.user.organization
        
        metrics = Sale.objects.filter(
            organization=org
        ).aggregate(
            total_revenue=Sum('final_total_price'),
            total_profit=Sum('total_profit'),
            transaction_count=Count('id')
        )
        
        return Response(metrics)


# ============================================================================
# TEMPLATE 8: Batch Operations Optimization
# ============================================================================

from django.db.models import F

def bulk_update_prices(request, branch_id):
    """Update multiple inventory items efficiently"""
    org = request.user.organization
    price_increase = 1.1  # 10% increase
    
    # Method 1: Direct database update (fastest)
    updated_count = Inventory.objects.filter(
        organization=org,
        branch_id=branch_id
    ).update(
        sale_price=F('sale_price') * price_increase
    )
    
    # Method 2: Batch create/update
    from django.db.models import F
    from bulk_update.helper import bulk_update
    
    inventory_items = Inventory.objects.filter(
        organization=org,
        branch_id=branch_id
    )
    
    for item in inventory_items:
        item.sale_price = item.sale_price * price_increase
    
    bulk_update(inventory_items, batch_size=1000)
    
    return JsonResponse({
        'updated': updated_count,
        'message': 'Prices updated successfully'
    })


# ============================================================================
# TEMPLATE 9: Query Debugging in Development
# ============================================================================

from django.test.utils import CaptureQueriesContext
from django.db import connection

def debug_view_queries(request):
    """Use this template to identify slow queries"""
    
    if not settings.DEBUG:
        return HttpResponse("Only available in DEBUG mode")
    
    with CaptureQueriesContext(connection) as context:
        # Your code here
        sales = Sale.objects.filter(
            organization=request.user.organization
        ).select_related('branch', 'staff')
        
        list(sales)  # Force evaluation
    
    # Print query analysis
    response = "<h2>Query Analysis</h2>"
    response += f"<p>Total queries: {len(context)}</p>"
    response += "<table border='1'>"
    response += "<tr><th>Query</th><th>Time</th></tr>"
    
    for query in context:
        response += f"<tr><td>{query['sql'][:200]}</td><td>{query['time']:.3f}s</td></tr>"
    
    response += "</table>"
    return HttpResponse(response)


# ============================================================================
# TEMPLATE 10: Settings File Configuration
# ============================================================================

# Add to ImsV3/settings.py for monitoring

if DEBUG:
    # Log all SQL queries
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
            },
        },
        'loggers': {
            'django.db.backends': {
                'handlers': ['console'],
                'level': 'DEBUG',  # Set to INFO in production
            },
        },
    }
    
    # Enable query statistics
    import sys
    if 'test' not in sys.argv:
        DEBUG_TOOLBAR_CONFIG = {
            'SHOW_TOOLBAR_CALLBACK': lambda r: DEBUG,
            'SHOW_TEMPLATE_CONTEXT': True,
            'ENABLE_STACKTRACES': True,
        }

# Monitor cache performance
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://localhost:6379/0',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'PARSER_KWARGS': {'encoding': 'utf8'},
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 50,
                'retry_on_timeout': True,
            },
            'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
        }
    }
}
