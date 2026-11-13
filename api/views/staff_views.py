from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import (
    ActivityLog,
    Branch,
    CustomUser,
    OrganizationMembership,
    STAFF_PERMISSION_CHOICES,
)
from account.utils import generate_secure_password
from api.context import resolve_mobile_context
from api.permissions import IsOwnerOnly, MOBILE_DEFAULT_PERMISSIONS
from api.serializers.staff import (
    StaffCreateSerializer,
    StaffMembershipSerializer,
    StaffUpdateSerializer,
)


class MobileStaffPermissionChoicesView(APIView):
    permission_classes = MOBILE_DEFAULT_PERMISSIONS

    @extend_schema(tags=["Staff"])
    def get(self, request):
        return Response(
            [{"key": key, "label": label} for key, label in STAFF_PERMISSION_CHOICES]
        )


class MobileStaffListCreateView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, IsOwnerOnly]

    @extend_schema(tags=["Staff"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        qs = (
            OrganizationMembership.objects.filter(organization=ctx.organization)
            .select_related("user", "branch")
            .order_by("date_joined")
        )
        branch_id = request.query_params.get("branch")
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        if request.query_params.get("active_only") == "true":
            qs = qs.filter(is_active=True)
        return Response(StaffMembershipSerializer(qs, many=True).data)

    @extend_schema(request=StaffCreateSerializer, tags=["Staff"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        serializer = StaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        branch = Branch.objects.filter(
            id=data["branch_id"], organization=ctx.organization
        ).first()
        if not branch:
            return Response(
                {"branch_id": ["Branch not found in your organization."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = data["email"].strip().lower()
        with transaction.atomic():
            user = CustomUser.objects.filter(email__iexact=email).first()
            temp_password = None
            if user:
                if OrganizationMembership.objects.filter(
                    user=user, organization=ctx.organization, is_active=True
                ).exists():
                    return Response(
                        {"email": ["This user is already an active member of this organization."]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                membership, _ = OrganizationMembership.objects.update_or_create(
                    user=user,
                    organization=ctx.organization,
                    defaults={
                        "branch": branch,
                        "role": data["role"],
                        "permissions": data.get("permissions", []),
                        "is_active": True,
                        "date_removed": None,
                    },
                )
            else:
                temp_password = data.get("password") or generate_secure_password(12)
                user = CustomUser.objects.create_user(
                    email=email,
                    password=temp_password,
                    first_name=data["first_name"].strip(),
                    last_name=data["last_name"].strip(),
                    phone_number=data.get("phone_number", "").strip(),
                    organization=ctx.organization,
                    branch=branch,
                    role=data["role"],
                    is_active=True,
                    must_change_password=True,
                )
                membership = OrganizationMembership.objects.create(
                    user=user,
                    organization=ctx.organization,
                    branch=branch,
                    role=data["role"],
                    permissions=data.get("permissions", []),
                    is_active=True,
                )

            ActivityLog.objects.create(
                organization=ctx.organization,
                branch=branch,
                staff=request.user,
                activity=f"Added staff {user.email} ({data['role']}) to {branch.name} via mobile API",
            )

        payload = StaffMembershipSerializer(membership).data
        if temp_password:
            payload["temporary_password"] = temp_password
        return Response(payload, status=status.HTTP_201_CREATED)


class MobileStaffDetailView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, IsOwnerOnly]

    def _get_membership(self, ctx, pk):
        return (
            OrganizationMembership.objects.filter(id=pk, organization=ctx.organization)
            .select_related("user", "branch")
            .first()
        )

    @extend_schema(tags=["Staff"])
    def get(self, request, pk):
        ctx = resolve_mobile_context(request)
        membership = self._get_membership(ctx, pk)
        if not membership:
            return Response({"detail": "Staff member not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(StaffMembershipSerializer(membership).data)

    @extend_schema(request=StaffUpdateSerializer, tags=["Staff"])
    def patch(self, request, pk):
        ctx = resolve_mobile_context(request)
        membership = self._get_membership(ctx, pk)
        if not membership:
            return Response({"detail": "Staff member not found."}, status=status.HTTP_404_NOT_FOUND)
        if membership.role == "owner":
            return Response(
                {"detail": "Owner membership cannot be modified via staff endpoint."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = StaffUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if "branch_id" in data:
            branch = Branch.objects.filter(
                id=data["branch_id"], organization=ctx.organization
            ).first()
            if not branch:
                return Response(
                    {"branch_id": ["Branch not found in your organization."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            membership.branch = branch
            if membership.user.organization_id == ctx.organization.id:
                membership.user.branch = branch
                membership.user.save(update_fields=["branch"])

        if "role" in data:
            membership.role = data["role"]
            if membership.user.organization_id == ctx.organization.id:
                membership.user.role = data["role"]
                membership.user.save(update_fields=["role"])

        if "permissions" in data:
            membership.permissions = data["permissions"]

        if "is_active" in data:
            membership.is_active = data["is_active"]

        membership.save()
        ActivityLog.objects.create(
            organization=ctx.organization,
            branch=membership.branch,
            staff=request.user,
            activity=f"Updated staff membership for {membership.user.email} via mobile API",
        )
        return Response(StaffMembershipSerializer(membership).data)

    @extend_schema(tags=["Staff"])
    def delete(self, request, pk):
        ctx = resolve_mobile_context(request)
        membership = self._get_membership(ctx, pk)
        if not membership:
            return Response({"detail": "Staff member not found."}, status=status.HTTP_404_NOT_FOUND)
        if membership.user_id == request.user.id or membership.role == "owner":
            return Response(
                {"detail": "Cannot deactivate the organization owner."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        membership.is_active = False
        membership.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)

