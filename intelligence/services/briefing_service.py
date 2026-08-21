from intelligence.core.briefing_engine import BriefingEngine
from intelligence.models import MorningBriefing
from account.models import Organization

class BriefingService:
    def __init__(self):
        self.engine = BriefingEngine()

    def run_daily_briefing(self, organization: Organization) -> MorningBriefing:
        """
        Triggers and saves morning report.
        """
        return self.engine.generate_briefing(organization)

    @staticmethod
    def get_latest_briefing(organization: Organization) -> MorningBriefing:
        """
        Returns latest available morning report.
        """
        return MorningBriefing.objects.filter(organization=organization).order_by('-date', '-created_at').first()
