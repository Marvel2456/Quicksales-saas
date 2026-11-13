from django.db.models import F, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Branch
from api.context import resolve_mobile_context
from api.permissions import IsOwnerOnly, MOBILE_DEFAULT_PERMISSIONS
from api.serializers.auth import BranchSummarySerializer
from ims.models import Inventory, Invoice, Sale


class BranchWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name", "address", "created_at"]
        read_only_fields = ["id", "created_at"]


class MobileDashboardSummaryView(APIView):
    permission_classes = MOBILE_DEFAULT_PERMISSIONS

    @extend_schema(tags=["Dashboard"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        sales_qs = Sale.objects.filter(
            organization=ctx.organization,
            completed=True,
            cancelled=False,
        )
        inv_qs = Inventory.objects.filter(organization=ctx.organization)
        invoice_qs = Invoice.objects.filter(organization=ctx.organization)

        if ctx.branch:
            sales_qs = sales_qs.filter(branch=ctx.branch)
            inv_qs = inv_qs.filter(branch=ctx.branch)
            invoice_qs = invoice_qs.filter(branch=ctx.branch)

        if ctx.role != "owner":
            invoice_qs = invoice_qs.filter(created_by=request.user)

        today_sales_qs = sales_qs.filter(date_added__gte=today_start)
        today_agg = today_sales_qs.aggregate(
            revenue=Sum("final_total_price"),
            profit=Sum("total_profit"),
        )

        low_stock_count = inv_qs.filter(
            quantity_available__lte=F("reorder_level")
        ).count()

        unpaid_invoices_count = invoice_qs.filter(
            status__in=["unpaid", "partial", "overdue"]
        ).count()

        recent_sales = list(
            sales_qs.order_by("-date_added")[:5].values(
                "id",
                "transaction_id",
                "final_total_price",
                "method",
                "date_added",
            )
        )

        return Response(
            {
                "organization": {
                    "id": str(ctx.organization.id),
                    "name": ctx.organization.name,
                    "currency_code": ctx.organization.currency_code,
                    "currency_symbol": ctx.organization.currency_symbol,
                },
                "branch": BranchSummarySerializer(ctx.branch).data if ctx.branch else None,
                "role": ctx.role,
                "permissions": ctx.permissions,
                "today_revenue": float(today_agg["revenue"] or 0),
                "today_profit": float(today_agg["profit"] or 0),
                "today_sales_count": today_sales_qs.count(),
                "low_stock_count": low_stock_count,
                "unpaid_invoices_count": unpaid_invoices_count,
                "recent_sales": recent_sales,
            }
        )


class MobileBranchListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [perm() for perm in [*MOBILE_DEFAULT_PERMISSIONS, IsOwnerOnly]]
        return [perm() for perm in MOBILE_DEFAULT_PERMISSIONS]

    @extend_schema(tags=["Branches"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        if ctx.role == "owner":
            branches = Branch.objects.filter(organization=ctx.organization).order_by("created_at")
        elif ctx.branch:
            branches = Branch.objects.filter(id=ctx.branch.id, organization=ctx.organization)
        else:
            branches = Branch.objects.none()
        return Response(BranchSummarySerializer(branches, many=True).data)

    @extend_schema(request=BranchWriteSerializer, tags=["Branches"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        serializer = BranchWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data["name"].strip()
        if Branch.objects.filter(organization=ctx.organization, name__iexact=name).exists():
            return Response(
                {"name": ["A branch with this name already exists in your organization."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        branch = Branch.objects.create(
            organization=ctx.organization,
            name=name,
            address=serializer.validated_data.get("address", ""),
        )
        return Response(BranchSummarySerializer(branch).data, status=status.HTTP_201_CREATED)


class MobileBranchDetailView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, IsOwnerOnly]

    @extend_schema(request=BranchWriteSerializer, tags=["Branches"])
    def patch(self, request, pk):
        ctx = resolve_mobile_context(request)
        branch = Branch.objects.filter(id=pk, organization=ctx.organization).first()
        if not branch:
            return Response({"detail": "Branch not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = BranchWriteSerializer(branch, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data.get("name")
        if name and Branch.objects.filter(
            organization=ctx.organization, name__iexact=name.strip()
        ).exclude(id=branch.id).exists():
            return Response(
                {"name": ["A branch with this name already exists in your organization."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer.save()
        return Response(BranchSummarySerializer(branch).data)

