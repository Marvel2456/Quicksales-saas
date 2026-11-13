from datetime import datetime

from django.db.models import Count, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import ActivityLog
from api.context import resolve_mobile_context
from api.pagination import paginate_queryset
from api.permissions import (
    HasActiveOrgMembership,
    HasRoleOrFeaturePermission,
    MOBILE_DEFAULT_PERMISSIONS,
    PasswordChangedPermission,
)
from ims.models import ErrorTicket, Sale, SalesItem
from subscriptions.models import Plan, Subscription


class ActivityLogSerializer(serializers.ModelSerializer):
    staff_email = serializers.EmailField(source="staff.email", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)

    class Meta:
        model = ActivityLog
        fields = ["id", "staff_email", "branch_id", "branch_name", "activity", "timestamp"]


class ErrorTicketSerializer(serializers.ModelSerializer):
    staff_email = serializers.EmailField(source="staff.email", read_only=True, default=None)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)

    class Meta:
        model = ErrorTicket
        fields = [
            "id",
            "title",
            "description",
            "status",
            "staff_email",
            "branch_id",
            "branch_name",
            "date_added",
            "date_updated",
        ]
        read_only_fields = [
            "id",
            "title",
            "description",
            "staff_email",
            "branch_id",
            "branch_name",
            "date_added",
            "date_updated",
        ]


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "id",
            "name",
            "tier",
            "size",
            "billing_frequency",
            "price",
            "price_usd",
            "duration_in_days",
            "max_branches",
            "max_users",
            "max_products",
            "has_online_store",
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    is_currently_valid = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan",
            "currency",
            "start_date",
            "end_date",
            "is_active",
            "is_currently_valid",
        ]

    def get_is_currently_valid(self, obj):
        return bool(obj.is_active and obj.end_date and obj.end_date >= timezone.now())


class MobileSalesReportSummaryView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(tags=["Reports"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        qs = Sale.objects.filter(
            organization=ctx.organization,
            completed=True,
            cancelled=False,
        )
        if ctx.branch:
            qs = qs.filter(branch=ctx.branch)

        start_str = request.query_params.get("start_date")
        end_str = request.query_params.get("end_date")
        if start_str:
            try:
                start_dt = timezone.make_aware(datetime.strptime(start_str, "%Y-%m-%d"))
                qs = qs.filter(date_added__gte=start_dt)
            except ValueError:
                return Response(
                    {"start_date": ["Expected YYYY-MM-DD format."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if end_str:
            try:
                end_dt = timezone.make_aware(
                    datetime.strptime(end_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                )
                qs = qs.filter(date_added__lte=end_dt)
            except ValueError:
                return Response(
                    {"end_date": ["Expected YYYY-MM-DD format."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        totals = qs.aggregate(
            total_revenue=Sum("final_total_price"),
            total_profit=Sum("total_profit"),
            total_discount=Sum("discount"),
            sales_count=Count("id"),
        )

        by_method = list(
            qs.values("method").annotate(
                count=Count("id"),
                revenue=Sum("final_total_price"),
            )
        )

        top_products = list(
            SalesItem.objects.filter(sale__in=qs, inventory__isnull=False)
            .values("inventory__product__product_name")
            .annotate(units_sold=Sum("quantity"), revenue=Sum("total"))
            .order_by("-units_sold")[:10]
        )

        return Response(
            {
                "total_revenue": float(totals["total_revenue"] or 0),
                "total_profit": float(totals["total_profit"] or 0),
                "total_discount": float(totals["total_discount"] or 0),
                "sales_count": totals["sales_count"] or 0,
                "by_method": by_method,
                "top_products": [
                    {
                        "product_name": row["inventory__product__product_name"],
                        "units_sold": row["units_sold"] or 0,
                        "revenue": float(row["revenue"] or 0),
                    }
                    for row in top_products
                ],
            }
        )


class MobileActivityLogListView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(tags=["Reports"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        qs = ActivityLog.objects.filter(organization=ctx.organization).select_related(
            "staff", "branch"
        )
        if ctx.branch:
            qs = qs.filter(branch=ctx.branch)
        return paginate_queryset(request, qs, ActivityLogSerializer)


class MobileErrorTicketListView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(tags=["Reports"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        qs = (
            ErrorTicket.objects.filter(organization=ctx.organization)
            .select_related("staff", "branch")
            .order_by("-date_added")
        )
        if ctx.branch:
            qs = qs.filter(branch=ctx.branch)
        ticket_status = request.query_params.get("status")
        if ticket_status:
            qs = qs.filter(status=ticket_status)
        return paginate_queryset(request, qs, ErrorTicketSerializer)


class MobileErrorTicketDetailView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(request=ErrorTicketSerializer, tags=["Reports"])
    def patch(self, request, pk):
        ctx = resolve_mobile_context(request)
        qs = ErrorTicket.objects.filter(id=pk, organization=ctx.organization)
        if ctx.branch and ctx.role != "owner":
            qs = qs.filter(branch=ctx.branch)
        ticket = qs.first()
        if not ticket:
            return Response({"detail": "Error ticket not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ErrorTicketSerializer(ticket, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class MobileCurrentSubscriptionView(APIView):
    permission_classes = [IsAuthenticated, PasswordChangedPermission, HasActiveOrgMembership]

    @extend_schema(tags=["Subscriptions"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        sub = (
            Subscription.objects.filter(organization=ctx.organization)
            .select_related("plan")
            .order_by("-end_date")
            .first()
        )
        if not sub:
            return Response({"subscription": None, "is_active": False})
        data = SubscriptionSerializer(sub).data
        return Response({"subscription": data, "is_active": data["is_currently_valid"]})


class MobilePlanListView(APIView):
    permission_classes = [IsAuthenticated, PasswordChangedPermission]

    @extend_schema(tags=["Subscriptions"])
    def get(self, request):
        plans = Plan.objects.all().order_by("price")
        return Response(PlanSerializer(plans, many=True).data)

