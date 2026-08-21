from typing import Dict, Any
from .base import BaseTool
from ims.services.inventory import InventoryService
from account.models import Organization, Branch

class GetInventorySummaryTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_inventory_summary"

    @property
    def description(self) -> str:
        return "Retrieves structured inventory status counts (total items count, low stock alert warning count)."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {}
        }

    def execute(self, args: Dict[str, Any], organization: Organization, branch: Branch = None) -> Any:
        metrics = InventoryService.get_inventory_summary(
            organization=organization,
            branch=branch
        )
        return metrics


class GetStockAuditTrailTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_stock_audit_trail"

    @property
    def description(self) -> str:
        return "Retrieves historical restock logs including date, product, quantity, cost price, and author."

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
                "product_name": {
                    "type": "string",
                    "description": "Optional product name query filter."
                }
            }
        }

    def execute(self, args: Dict[str, Any], organization: Organization, branch: Branch = None) -> Any:
        start_date = args.get('start_date')
        end_date = args.get('end_date')
        product_name = args.get('product_name')
        
        audit_qs = InventoryService.get_stock_audit_trail(
            organization=organization,
            branch=branch,
            start_date=start_date,
            end_date=end_date,
            product_name=product_name
        )
        
        return [
            {
                'product_name': a.product.product_name,
                'restocked_by': str(a.history_user) if a.history_user else 'System',
                'date_restocked': str(a.history_date),
                'quantity_restocked': a.quantity_restocked,
                'new_cost_price': float(a.cost_price),
                'new_sale_price': float(a.sale_price)
            }
            for a in audit_qs[:15]
        ]
