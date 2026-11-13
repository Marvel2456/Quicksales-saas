from dataclasses import dataclass
from typing import List, Optional
import uuid

from rest_framework.exceptions import PermissionDenied, ValidationError

from account.models import (
    Branch,
    Organization,
    OrganizationMembership,
    VALID_STAFF_PERMISSION_KEYS,
)


@dataclass
class MobileContext:
    organization: Optional[Organization]
    branch: Optional[Branch]
    membership: Optional[OrganizationMembership]
    role: Optional[str]
    permissions: List[str]


def _parse_uuid(raw_value, header_name):
    if not raw_value:
        return None
    try:
        return uuid.UUID(str(raw_value).strip())
    except (ValueError, TypeError):
        raise ValidationError({header_name: f"Invalid UUID in {header_name} header."})


def resolve_mobile_context(request) -> MobileContext:
    """Resolve organization, branch, membership, role, and feature permissions for a mobile API request."""
    cached = getattr(request, "_mobile_ctx", None)
    if cached is not None:
        return cached

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        ctx = MobileContext(None, None, None, None, [])
        request._mobile_ctx = ctx
        return ctx

    org_header = request.headers.get("X-Organization-ID")
    org_uuid = _parse_uuid(org_header, "X-Organization-ID")

    membership = None
    organization = None

    if org_uuid:
        membership = (
            OrganizationMembership.objects.filter(
                user=user,
                organization_id=org_uuid,
                is_active=True,
            )
            .select_related("organization", "branch")
            .first()
        )
        if membership:
            organization = membership.organization
        elif user.organization_id == org_uuid:
            organization = user.organization
        else:
            raise PermissionDenied("You do not have active access to the requested organization.")
    else:
        if user.organization_id:
            membership = (
                OrganizationMembership.objects.filter(
                    user=user,
                    organization_id=user.organization_id,
                    is_active=True,
                )
                .select_related("organization", "branch")
                .first()
            )
            organization = membership.organization if membership else user.organization
        if organization is None:
            membership = (
                OrganizationMembership.objects.filter(
                    user=user,
                    is_active=True,
                )
                .select_related("organization", "branch")
                .first()
            )
            if membership:
                organization = membership.organization

    role = membership.role if membership else getattr(user, "role", None)

    branch_header = request.headers.get("X-Branch-ID")
    branch_uuid = _parse_uuid(branch_header, "X-Branch-ID")

    assigned_branch = (membership.branch if membership and membership.branch_id else None)
    if assigned_branch is None and user.branch_id and (
        not organization or user.branch.organization_id == organization.id
    ):
        assigned_branch = user.branch

    if branch_uuid and organization:
        if role == "owner":
            branch = Branch.objects.filter(id=branch_uuid, organization=organization).first()
            if not branch:
                raise PermissionDenied("Requested branch does not belong to the active organization.")
        else:
            if not assigned_branch or str(assigned_branch.id) != str(branch_uuid):
                raise PermissionDenied("You are only permitted to access your assigned branch.")
            branch = assigned_branch
    else:
        branch = assigned_branch
        if branch is None and role == "owner" and organization:
            branch = Branch.objects.filter(organization=organization).order_by("created_at").first()

    if role == "owner":
        permissions = sorted(VALID_STAFF_PERMISSION_KEYS)
    elif hasattr(user, "get_permissions_in_organization") and organization:
        permissions = sorted(user.get_permissions_in_organization(organization=organization, branch=branch))
    else:
        permissions = []

    ctx = MobileContext(
        organization=organization,
        branch=branch,
        membership=membership,
        role=role,
        permissions=permissions,
    )
    request._mobile_ctx = ctx
    return ctx

