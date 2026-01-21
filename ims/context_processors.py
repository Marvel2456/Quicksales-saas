from django.db.models import Q

from ims.models import ErrorTicket


def ticket_notifications(request):
    """Provide pending ticket count for navbar badge across all pages."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"pending_ticket_count": 0}

    organization = getattr(user, "organization", None)
    if not organization:
        return {"pending_ticket_count": 0}

    qs = ErrorTicket.objects.filter(organization=organization, status="Pending")
    if user.role not in ["owner", "manager"]:
        qs = qs.filter(Q(staff=user) | Q(assigned_to=user))

    return {"pending_ticket_count": qs.count()}
