import secrets
import string
from django.core.exceptions import ValidationError

from account.models import Branch, OrganizationMembership


def generate_secure_password(length=12):
    """Generate a secure random password"""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def get_request_organization(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None

    organization = getattr(request, "organization", None)
    if organization:
        return organization

    org_id = request.session.get("active_organization_id")
    if org_id:
        try:
            membership = OrganizationMembership.objects.filter(
                user=user,
                organization_id=org_id,
                is_active=True,
            ).select_related("organization").first()
            if membership:
                return membership.organization
        except (ValidationError, ValueError, TypeError):
            # Stale or malformed session value (e.g., pre-UUID IDs): clear and fallback.
            request.session.pop("active_organization_id", None)

    return getattr(user, "organization", None)


def get_request_org_role(request, organization=None):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None

    if organization is None:
        organization = get_request_organization(request)

    if organization:
        membership = OrganizationMembership.objects.filter(
            user=user,
            organization=organization,
            is_active=True,
        ).first()
        if membership:
            return membership.role

    return getattr(user, "role", None)


def get_request_branch(request, organization=None):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None

    if organization is None:
        organization = get_request_organization(request)

    if organization:
        active_branch_id = request.session.get("active_branch_id")
        if active_branch_id:
            try:
                branch_obj = Branch.objects.filter(
                    id=active_branch_id,
                    organization=organization,
                ).first()
                if branch_obj:
                    return branch_obj
            except (ValidationError, ValueError, TypeError):
                # Stale or malformed session value (e.g., pre-UUID IDs): clear and fallback.
                request.session.pop("active_branch_id", None)

        membership = OrganizationMembership.objects.filter(
            user=user,
            organization=organization,
            is_active=True,
        ).select_related("branch").first()
        if membership:
            return membership.branch

    branch = getattr(request, "branch", None)
    if branch and (not organization or branch.organization_id == organization.id):
        return branch

    return getattr(user, "branch", None)
