from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission, IsAuthenticated

from api.context import resolve_mobile_context
from subscriptions.models import Subscription


class SubscriptionRequiredException(APIException):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = "Active subscription required to access this resource."
    default_code = "subscription_expired"


class PasswordChangeRequiredException(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Password change is required before accessing this resource."
    default_code = "password_change_required"


class PasswordChangedPermission(BasePermission):
    """Blocks access with 403 JSON if the authenticated user must change their password."""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "must_change_password", False):
            raise PasswordChangeRequiredException()
        return True


class HasActiveOrgMembership(BasePermission):
    """Requires the user to belong to an active organization resolved via headers or default."""

    message = "No active organization membership found."

    def has_permission(self, request, view):
        ctx = resolve_mobile_context(request)
        return ctx.organization is not None


class SubscriptionActivePermission(BasePermission):
    """Enforces an active, non-expired subscription for the resolved organization."""

    def has_permission(self, request, view):
        ctx = resolve_mobile_context(request)
        if not ctx.organization:
            return False
        sub = Subscription.objects.filter(
            organization=ctx.organization,
            is_active=True,
            end_date__gte=timezone.now(),
        ).first()
        if not sub:
            raise SubscriptionRequiredException()
        request.subscription = sub
        return True


class IsOwnerOnly(BasePermission):
    """Allows access only to organization owners."""

    message = "Only organization owners can perform this action."

    def has_permission(self, request, view):
        ctx = resolve_mobile_context(request)
        return ctx.role == "owner"


class HasRoleOrFeaturePermission(BasePermission):
    """
    Allows access if the user's role is in `allowed_roles` OR if the user has any
    feature permission listed in `required_feature_permissions` for the active org & branch.
    Views can set `allowed_roles` (tuple/list) and `required_feature_permissions` (tuple/list).
    """

    message = "You do not have permission to access this feature."

    def has_permission(self, request, view):
        ctx = resolve_mobile_context(request)
        if not ctx.organization:
            return False
        if ctx.role == "owner":
            return True

        allowed_roles = getattr(view, "allowed_roles", ())
        if ctx.role in allowed_roles:
            return True

        required_features = getattr(view, "required_feature_permissions", ())
        return any(perm in ctx.permissions for perm in required_features)


MOBILE_DEFAULT_PERMISSIONS = [
    IsAuthenticated,
    PasswordChangedPermission,
    HasActiveOrgMembership,
    SubscriptionActivePermission,
]
