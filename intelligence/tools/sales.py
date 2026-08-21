from typing import Dict, Any
from .base import BaseTool
from ims.services.sales import SalesService
from account.models import Organization, Branch

class GetSalesSummaryTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_sales_summary"

    @property
    def description(self) -> str:
        return "Retrieves aggregated sales metrics (total sales value, total profit value, total transactions count) over a date range."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Optional ISO format start date (e.g. YYYY-MM-DD)."
                },
                "end_date": {
                    "type": "string",
                    "description": "Optional ISO format end date (e.g. YYYY-MM-DD)."
                },
                "method": {
                    "type": "string",
                    "description": "Optional payment method filter (e.g. cash, card, transfer)."
                }
            }
        }

    def execute(self, args: Dict[str, Any], organization: Organization, branch: Branch = None) -> Any:
        start_date = args.get('start_date')
        end_date = args.get('end_date')
        method = args.get('method')
        
        sales_qs = SalesService.get_sales_summary(
            organization=organization,
            branch=branch,
            start_date=start_date,
            end_date=end_date,
            method=method
        )
        metrics = SalesService.get_aggregated_metrics(sales_qs)
        
        return {
            'total_sales': float(metrics['total_sales']),
            'total_profit': float(metrics['total_profit']),
            'total_quantity': metrics['total_quantity'],
            'transaction_count': sales_qs.count()
        }


class GetTopProductsTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_top_selling_products"

    @property
    def description(self) -> str:
        return "Retrieves the list of top-selling products by quantity sold."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of products to return (default 5)."
                }
            }
        }

    def execute(self, args: Dict[str, Any], organization: Organization, branch: Branch = None) -> Any:
        limit = args.get('limit', 5)
        top_selling = SalesService.get_top_selling_products(
            organization=organization,
            branch=branch,
            limit=limit
        )
        return [
            {
                'product_name': p['product__product_name'],
                'quantity_sold': p['qty_sold'],
                'total_revenue': float(p['total_revenue'])
            }
            for p in top_selling
        ]
