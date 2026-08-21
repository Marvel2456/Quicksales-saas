from typing import List
from intelligence.core.insight_engine import InsightEngine
from intelligence.models import UserInsight
from account.models import Organization, Branch

class InsightService:
    def __init__(self):
        self.engine = InsightEngine()

    def run_insights_scan(self, organization: Organization, branch: Branch = None) -> int:
        """
        Triggers LLM-driven background analytical scans.
        """
        return self.engine.generate_insights(organization, branch)

    @staticmethod
    def get_insights(organization: Organization, branch: Branch = None, unread_only: bool = False) -> List[UserInsight]:
        """
        Fetches insights list for displaying in dashboard widget.
        """
        qs = UserInsight.objects.filter(organization=organization)
        if branch:
            qs = qs.filter(branch=branch)
        if unread_only:
            qs = qs.filter(is_read=False)
        return list(qs)

    @staticmethod
    def mark_as_read(insight_id: str, organization: Organization) -> bool:
        """
        Marks warning insight alert as read.
        """
        try:
            insight = UserInsight.objects.get(id=insight_id, organization=organization)
            insight.is_read = True
            insight.save()
            return True
        except UserInsight.DoesNotExist:
            return False
