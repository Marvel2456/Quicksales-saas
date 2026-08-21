import json
from django.utils import timezone
from intelligence.core.provider_factory import ProviderFactory
from intelligence.models import UserInsight
from ims.services.sales import SalesService
from ims.services.inventory import InventoryService
from account.models import Organization, Branch

class InsightEngine:
    def __init__(self):
        self.provider = ProviderFactory.get_provider()

    def generate_insights(self, organization: Organization, branch: Branch = None) -> int:
        """
        Collects metrics, feeds them to the provider for anomaly detection, and stores the resulting insights.
        """
        # 1. Fetch raw transaction metrics for last 7 days
        sales_summary = SalesService.get_sales_summary(
            organization=organization,
            branch=branch,
            start_date=timezone.now() - timezone.timedelta(days=7)
        )
        sales_metrics = SalesService.get_aggregated_metrics(sales_summary)
        
        # Top selling products
        top_products = SalesService.get_top_selling_products(
            organization=organization,
            branch=branch,
            limit=5
        )
        top_products_list = [
            {'product': p['product__product_name'], 'quantity': p['qty_sold']}
            for p in top_products
        ]

        # Inventory summaries
        inventory_summary = InventoryService.get_inventory_summary(
            organization=organization,
            branch=branch
        )

        # 2. Build Prompt
        system_instruction = (
            "You are the MarvexQS Analytics Engine, an AI designed to analyze retail metrics and detect trends, stock issues, "
            "and anomalies. Output a valid JSON list of insights. Each insight must contain: "
            "'title' (string), 'content' (detailed analysis string), and 'insight_type' (one of: 'info', 'warning', 'success', 'error'). "
            "Be specific, numbers-driven, and brief. Never output markdown codeblocks. Output raw JSON only."
        )

        data_payload = {
            'organization': organization.name,
            'branch': branch.name if branch else 'All Branches',
            'time_period': 'Last 7 Days',
            'metrics': {
                'total_sales_value': float(sales_metrics['total_sales']),
                'total_profit_value': float(sales_metrics['total_profit']),
                'total_transactions': sales_summary.count()
            },
            'top_products': top_products_list,
            'inventory': {
                'total_items': inventory_summary['total_items'],
                'low_stock_items': inventory_summary['low_stock_count']
            }
        }

        prompt = f"Analyze the following retail data and generate valuable business insights or warning indicators:\n{json.dumps(data_payload, indent=2)}"

        try:
            response = self.provider.generate_response(
                prompt=prompt,
                system_instruction=system_instruction,
                history=[]
            )
            
            raw_text = response.get('text', '').strip()
            # Strip markdown formatting if any
            if raw_text.startswith("```json"):
                raw_text = raw_text.replace("```json", "", 1)
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()

            insights_list = json.loads(raw_text)
            
            created_count = 0
            if isinstance(insights_list, list):
                for ins in insights_list:
                    title = ins.get('title')
                    content = ins.get('content')
                    itype = ins.get('insight_type', 'info')
                    
                    if title and content:
                        UserInsight.objects.create(
                            organization=organization,
                            branch=branch,
                            title=title,
                            content=content,
                            insight_type=itype
                        )
                        created_count += 1
            return created_count
        except Exception as e:
            # Fallback error logger
            UserInsight.objects.create(
                organization=organization,
                branch=branch,
                title="AI Analytics Engine Notice",
                content=f"Encountered error during automated analytical scan: {str(e)}",
                insight_type="error"
            )
            return 0
