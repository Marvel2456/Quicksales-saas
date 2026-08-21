from django.utils import timezone
from ims.services.sales import SalesService
from ims.services.inventory import InventoryService
from account.models import Organization, Branch

class BusinessHealthService:
    @staticmethod
    def get_health_metrics(organization: Organization, branch: Branch = None) -> dict:
        """
        Retrieves real-time daily operational performance KPIs.
        """
        today = timezone.now().date()
        sales_summary = SalesService.get_sales_summary(
            organization=organization,
            branch=branch,
            start_date=today
        )
        sales_metrics = SalesService.get_aggregated_metrics(sales_summary)
        inventory_summary = InventoryService.get_inventory_summary(
            organization=organization,
            branch=branch
        )

        return {
            'today_sales': float(sales_metrics['total_sales']),
            'today_profit': float(sales_metrics['total_profit']),
            'today_transactions': sales_summary.count(),
            'total_stock_items': inventory_summary['total_items'],
            'low_stock_warnings': inventory_summary['low_stock_count']
        }
