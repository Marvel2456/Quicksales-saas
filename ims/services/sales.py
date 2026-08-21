from datetime import datetime, date
from django.db.models import Sum, Count, Q
from ims.models import Sale, SalesItem

class SalesService:
    @staticmethod
    def get_sales_summary(organization, branch=None, start_date=None, end_date=None, status=None, method=None, rep=None):
        """
        Generic sales query filter and aggregator.
        Ensures tenant boundaries by requiring organization.
        """
        sales_qs = Sale.objects.filter(organization=organization)
        if branch:
            sales_qs = sales_qs.filter(branch=branch)
            
        if start_date:
            sales_qs = sales_qs.filter(date_updated__date__gte=start_date)
        if end_date:
            sales_qs = sales_qs.filter(date_updated__date__lte=end_date)
        if rep:
            sales_qs = sales_qs.filter(staff__first_name__icontains=rep)
        if method:
            sales_qs = sales_qs.filter(method=method)
            
        if status:
            if status == 'completed':
                sales_qs = sales_qs.filter(completed=True, cancelled=False)
            elif status == 'cancelled':
                sales_qs = sales_qs.filter(cancelled=True)
            elif status == 'open':
                sales_qs = sales_qs.filter(completed=False, cancelled=False)
                
        return sales_qs

    @staticmethod
    def get_aggregated_metrics(sales_qs):
        """
        Computes aggregates on a pre-filtered sales queryset.
        """
        agg = sales_qs.aggregate(
            total_sales=Sum('final_total_price'),
            total_profit=Sum('total_profit'),
            transaction_count=Count('id')
        )
        total_sales = agg.get('total_sales') or 0.0
        total_profit = agg.get('total_profit') or 0.0
        transaction_count = agg.get('transaction_count') or 0
        total_quantity = sum(s.get_cart_items for s in sales_qs)
        
        return {
            'total_sales': total_sales,
            'total_profit': total_profit,
            'transaction_count': transaction_count,
            'total_quantity': total_quantity
        }

    @staticmethod
    def get_top_selling_products(branch, limit=5):
        """
        Aggregates top selling products by quantity for a branch.
        """
        return (
            SalesItem.objects.filter(branch=branch)
            .values('inventory__product__product_name')
            .annotate(total_quantity=Sum('quantity'))
            .order_by('-total_quantity')[:limit]
        )

    @staticmethod
    def get_monthly_sales_and_profits(branch, year):
        """
        Gets monthly sales and profits for a given branch and year.
        """
        sales_by_month = (
            Sale.objects.filter(branch=branch, date_added__year=year)
            .values('date_added__month')
            .annotate(total_sales=Sum('final_total_price'), total_profit=Sum('total_profit'))
            .order_by('date_added__month')
        )
        return sales_by_month

    @staticmethod
    def get_daily_sales_and_profits(branch, year, month):
        """
        Gets daily sales and profits for a given branch, year, and month.
        """
        daily_stats = (
            Sale.objects.filter(
                branch=branch,
                date_added__year=year,
                date_added__month=month
            )
            .values('date_added__day')
            .annotate(daily_revenue=Sum('final_total_price'), daily_profit=Sum('total_profit'))
            .order_by('date_added__day')
        )
        return daily_stats

    @staticmethod
    def get_recent_high_quantity_sales(branch, limit=7):
        """
        Gets recent sales items sorted by highest quantity.
        """
        return SalesItem.objects.filter(branch=branch).select_related(
            'inventory__product'
        ).order_by('-quantity')[:limit]
