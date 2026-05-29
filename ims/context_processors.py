from django.db.models import Q
import logging

from ims.models import ErrorTicket


logger = logging.getLogger(__name__)


def ticket_notifications(request):
    """Provide pending ticket count for navbar badge across all pages."""
    try:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return {"pending_ticket_count": 0}

        organization = getattr(request, "organization", None) or getattr(user, "organization", None)
        if not organization:
            return {"pending_ticket_count": 0}

        qs = ErrorTicket.objects.filter(organization=organization, status="Pending")
        if getattr(user, "role", None) not in ["owner", "manager"]:
            qs = qs.filter(Q(staff=user) | Q(assigned_to=user))

        return {"pending_ticket_count": qs.count()}
    except Exception:
        logger.exception("ticket_notifications context processor failed")
        return {"pending_ticket_count": 0}
