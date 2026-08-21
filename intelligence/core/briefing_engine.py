import json
from django.utils import timezone
from intelligence.core.provider_factory import ProviderFactory
from intelligence.models import MorningBriefing
from ims.services.sales import SalesService
from ims.services.inventory import InventoryService
from account.models import Organization

class BriefingEngine:
    def __init__(self):
        self.provider = ProviderFactory.get_provider()

    def generate_briefing(self, organization: Organization) -> MorningBriefing:
        """
        Synthesizes the organization's business metrics into an executive morning briefing.
        """
        today = timezone.now().date()
        
        # Fetch today's sales summary
        sales_summary = SalesService.get_sales_summary(
            organization=organization,
            start_date=today
        )
        sales_metrics = SalesService.get_aggregated_metrics(sales_summary)
        
        # Fetch inventory summary
        inventory_summary = InventoryService.get_inventory_summary(
            organization=organization
        )

        system_instruction = (
            "You are the MarvexQS Chief Intelligence Officer. Synthesize the provided day's performance "
            "metrics into a neat, encouraging, and narrative daily business executive briefing. "
            "Address key metrics like sales totals, margins, and low stock warnings. "
            "Structure using clean markdown headers. Keep the length moderate and easy to scan."
        )

        data_payload = {
            'organization': organization.name,
            'date': str(today),
            'metrics': {
                'sales_value': float(sales_metrics['total_sales']),
                'profit_value': float(sales_metrics['total_profit']),
                'transaction_count': sales_summary.count()
            },
            'inventory_summary': {
                'low_stock_count': inventory_summary['low_stock_count']
            }
        }

        prompt = f"Synthesize today's metrics into the morning briefing:\n{json.dumps(data_payload, indent=2)}"

        try:
            response = self.provider.generate_response(
                prompt=prompt,
                system_instruction=system_instruction,
                history=[]
            )
            
            content = response.get('text', 'No summary generated.')
            
            return MorningBriefing.objects.create(
                organization=organization,
                title=f"Morning Briefing for {today.strftime('%b %d, %Y')}",
                content=content,
                date=today
            )
        except Exception as e:
            return MorningBriefing.objects.create(
                organization=organization,
                title=f"Morning Briefing for {today.strftime('%b %d, %Y')} (Fallback)",
                content=f"Could not retrieve AI Briefing today due to communication error: {str(e)}",
                date=today
            )
