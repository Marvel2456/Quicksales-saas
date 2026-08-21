from celery import shared_task
from account.models import Organization
from intelligence.services.insight_service import InsightService
from intelligence.services.briefing_service import BriefingService

@shared_task
def generate_nightly_insights():
    """
    Celery task running nightly to scan all organizations for stock levels and anomalies.
    """
    organizations = Organization.objects.all()
    insight_service = InsightService()
    
    for org in organizations:
        # Run analytical sweep for each active tenant
        insight_service.run_insights_scan(org)


@shared_task
def generate_daily_briefings():
    """
    Celery task running daily at 06:00 to pre-generate briefings for active tenant dashboards.
    """
    organizations = Organization.objects.all()
    briefing_service = BriefingService()
    
    for org in organizations:
        briefing_service.run_daily_briefing(org)


@shared_task
def generate_organization_briefing_task(organization_id):
    """
    On-demand asynchronous Celery task to generate daily briefing for a specific organization.
    """
    try:
        org = Organization.objects.get(id=organization_id)
        briefing_service = BriefingService()
        briefing_service.run_daily_briefing(org)
    except Exception:
        pass


@shared_task
def generate_branch_insights_task(organization_id, branch_id):
    """
    On-demand asynchronous Celery task to scan insights for a specific branch.
    """
    try:
        from account.models import Branch
        org = Organization.objects.get(id=organization_id)
        branch = Branch.objects.get(id=branch_id)
        insight_service = InsightService()
        insight_service.run_insights_scan(org, branch)
    except Exception:
        pass
