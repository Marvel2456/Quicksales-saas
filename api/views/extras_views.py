from datetime import datetime

from django.db.models import Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import ActivityLog, CustomUser
from api.context import resolve_mobile_context
from api.pagination import paginate_list, paginate_queryset
from api.permissions import (
    HasRoleOrFeaturePermission,
    IsOwnerOnly,
    MOBILE_DEFAULT_PERMISSIONS,
)
from ims.models import ErrorTicket, Inventory, Sale, SalesItem, TicketComment
from ims.services.inventory import InventoryService


class TicketCommentSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source="author.email", read_only=True)
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = TicketComment
        fields = ["id", "author_id", "author_email", "author_name", "content", "created_at"]

    def get_author_name(self, obj):
        name = f"{obj.author.first_name} {obj.author.last_name}".strip()
        return name or obj.author.email


class TicketDetailSerializer(serializers.ModelSerializer):
    staff_email = serializers.EmailField(source="staff.email", read_only=True, default=None)
    assigned_to_email = serializers.EmailField(
        source="assigned_to.email", read_only=True, default=None
    )
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    comments = TicketCommentSerializer(many=True, read_only=True)

    class Meta:
        model = ErrorTicket
        fields = [
            "id",
            "title",
            "description",
            "status",
            "staff_id",
            "staff_email",
            "assigned_to",
            "assigned_to_email",
            "branch_id",
            "branch_name",
            "date_added",
            "date_updated",
            "comments",
        ]


class TicketCreateInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=150)
    description = serializers.CharField()
    assigned_to = serializers.UUIDField(required=False, allow_null=True)


class TicketUpdateInputSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["Pending", "Seen"], required=False)
    assigned_to = serializers.UUIDField(required=False, allow_null=True)


class TicketCommentInputSerializer(serializers.Serializer):
    content = serializers.CharField()


class BulkCountItemSerializer(serializers.Serializer):
    inventory_id = serializers.UUIDField()
    counted_quantity = serializers.IntegerField(min_value=0)


class BulkCountInputSerializer(serializers.Serializer):
    items = BulkCountItemSerializer(many=True)


class MobilePriceAuditView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, IsOwnerOnly]

    @extend_schema(tags=["Inventory & Audit"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        product_query = request.query_params.get("product")

        audits = InventoryService.get_stock_audit_trail(
            organization=ctx.organization,
            branch=ctx.branch,
            start_date=start_date,
            end_date=end_date,
            product_name=product_query,
        ).select_related("product", "history_user", "branch")

        results = []
        for record in audits[:250]:
            user = record.history_user
            user_name = (
                f"{user.first_name} {user.last_name}".strip() or user.email
                if user
                else None
            )
            results.append(
                {
                    "history_id": record.history_id,
                    "inventory_id": str(record.id),
                    "product_id": str(record.product_id) if record.product_id else None,
                    "product_name": record.product.product_name if record.product else None,
                    "branch_id": str(record.branch_id) if record.branch_id else None,
                    "branch_name": record.branch.name if record.branch else None,
                    "staff_name": user_name,
                    "quantity_restocked": record.quantity_restocked,
                    "quantity": record.quantity,
                    "cost_price": record.cost_price,
                    "sale_price": record.sale_price,
                    "history_date": record.history_date,
                }
            )
        return paginate_list(request, results)


class MobileTicketListCreateView(APIView):
    permission_classes = MOBILE_DEFAULT_PERMISSIONS

    @extend_schema(tags=["Tickets"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        qs = (
            ErrorTicket.objects.filter(organization=ctx.organization)
            .select_related("staff", "assigned_to", "branch")
            .prefetch_related("comments__author")
            .order_by("-date_added")
        )
        if ctx.role in ("owner", "manager"):
            if ctx.branch:
                qs = qs.filter(branch=ctx.branch)
        else:
            qs = qs.filter(Q(staff=request.user) | Q(assigned_to=request.user))

        ticket_status = request.query_params.get("status")
        if ticket_status:
            qs = qs.filter(status=ticket_status)

        return paginate_queryset(request, qs, TicketDetailSerializer)

    @extend_schema(request=TicketCreateInputSerializer, tags=["Tickets"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        serializer = TicketCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        assigned_user = None
        if data.get("assigned_to"):
            assigned_user = CustomUser.objects.filter(
                id=data["assigned_to"],
                memberships__organization=ctx.organization,
                memberships__is_active=True,
            ).first()
            if not assigned_user:
                return Response(
                    {"assigned_to": ["Assigned user is not an active member of this organization."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        ticket = ErrorTicket.objects.create(
            organization=ctx.organization,
            branch=ctx.branch,
            staff=request.user,
            assigned_to=assigned_user,
            title=data["title"].strip(),
            description=data["description"].strip(),
            status="Pending",
        )
        return Response(TicketDetailSerializer(ticket).data, status=status.HTTP_201_CREATED)


class MobileTicketDetailView(APIView):
    permission_classes = MOBILE_DEFAULT_PERMISSIONS

    def _get_ticket(self, request, ctx, pk):
        qs = (
            ErrorTicket.objects.filter(id=pk, organization=ctx.organization)
            .select_related("staff", "assigned_to", "branch")
            .prefetch_related("comments__author")
        )
        ticket = qs.first()
        if not ticket:
            return None, False
        if ctx.role in ("owner", "manager"):
            return ticket, True
        if ticket.staff_id == request.user.id or ticket.assigned_to_id == request.user.id:
            return ticket, True
        return None, False

    @extend_schema(tags=["Tickets"])
    def get(self, request, pk):
        ctx = resolve_mobile_context(request)
        ticket, allowed = self._get_ticket(request, ctx, pk)
        if not ticket:
            return Response({"detail": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)
        if not allowed:
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
        return Response(TicketDetailSerializer(ticket).data)

    @extend_schema(request=TicketUpdateInputSerializer, tags=["Tickets"])
    def patch(self, request, pk):
        ctx = resolve_mobile_context(request)
        if ctx.role not in ("owner", "manager"):
            return Response(
                {"detail": "Only owners and managers can update ticket status or assignment."},
                status=status.HTTP_403_FORBIDDEN,
            )
        ticket = (
            ErrorTicket.objects.filter(id=pk, organization=ctx.organization)
            .select_related("staff", "assigned_to", "branch")
            .prefetch_related("comments__author")
            .first()
        )
        if not ticket:
            return Response({"detail": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = TicketUpdateInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if "status" in data:
            ticket.status = data["status"]
        if "assigned_to" in data:
            if data["assigned_to"] is None:
                ticket.assigned_to = None
            else:
                assigned_user = CustomUser.objects.filter(
                    id=data["assigned_to"],
                    memberships__organization=ctx.organization,
                    memberships__is_active=True,
                ).first()
                if not assigned_user:
                    return Response(
                        {"assigned_to": ["User is not an active member of this organization."]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                ticket.assigned_to = assigned_user
        ticket.save()
        return Response(TicketDetailSerializer(ticket).data)


class MobileTicketCommentCreateView(APIView):
    permission_classes = MOBILE_DEFAULT_PERMISSIONS

    @extend_schema(request=TicketCommentInputSerializer, tags=["Tickets"])
    def post(self, request, pk):
        ctx = resolve_mobile_context(request)
        ticket = ErrorTicket.objects.filter(id=pk, organization=ctx.organization).first()
        if not ticket:
            return Response({"detail": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)
        if ctx.role not in ("owner", "manager") and ticket.staff_id != request.user.id and ticket.assigned_to_id != request.user.id:
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        serializer = TicketCommentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = TicketComment.objects.create(
            ticket=ticket,
            author=request.user,
            content=serializer.validated_data["content"].strip(),
        )
        return Response(TicketCommentSerializer(comment).data, status=status.HTTP_201_CREATED)


class MobileProfitReportView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(tags=["Reports"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        sales_qs = Sale.objects.filter(
            organization=ctx.organization,
            completed=True,
            cancelled=False,
        )
        if ctx.branch:
            sales_qs = sales_qs.filter(branch=ctx.branch)

        start_str = request.query_params.get("start_date")
        end_str = request.query_params.get("end_date")
        if start_str:
            try:
                sales_qs = sales_qs.filter(
                    date_added__gte=timezone.make_aware(datetime.strptime(start_str, "%Y-%m-%d"))
                )
            except ValueError:
                return Response(
                    {"start_date": ["Expected YYYY-MM-DD format."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if end_str:
            try:
                sales_qs = sales_qs.filter(
                    date_added__lte=timezone.make_aware(
                        datetime.strptime(end_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                    )
                )
            except ValueError:
                return Response(
                    {"end_date": ["Expected YYYY-MM-DD format."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        items_qs = SalesItem.objects.filter(sale__in=sales_qs)
        item_agg = items_qs.aggregate(
            total_revenue=Sum("total"),
            total_cost=Sum("cost_total"),
        )
        sales_agg = sales_qs.aggregate(
            net_revenue=Sum("final_total_price"),
            total_profit=Sum("total_profit"),
        )
        net_rev = float(sales_agg["net_revenue"] or 0.0)
        tot_profit = float(sales_agg["total_profit"] or 0.0)
        tot_cost = float(item_agg["total_cost"] or 0.0)
        margin_pct = round((tot_profit / net_rev) * 100, 2) if net_rev > 0 else 0.0

        by_day = list(
            sales_qs.annotate(day=TruncDate("date_added"))
            .values("day")
            .annotate(revenue=Sum("final_total_price"), profit=Sum("total_profit"))
            .order_by("day")
        )

        by_product_raw = list(
            items_qs.filter(inventory__isnull=False)
            .values("inventory__product__product_name")
            .annotate(
                units_sold=Sum("quantity"),
                revenue=Sum("total"),
                cost=Sum("cost_total"),
            )
            .order_by("-revenue")[:20]
        )
        by_product = []
        for row in by_product_raw:
            rev = float(row["revenue"] or 0.0)
            cost = float(row["cost"] or 0.0)
            by_product.append(
                {
                    "product_name": row["inventory__product__product_name"],
                    "units_sold": row["units_sold"] or 0,
                    "revenue": rev,
                    "cost": cost,
                    "profit": round(rev - cost, 2),
                }
            )

        return Response(
            {
                "total_revenue": net_rev,
                "total_cost": tot_cost,
                "total_profit": tot_profit,
                "profit_margin_percent": margin_pct,
                "by_day": [
                    {
                        "date": str(d["day"]),
                        "revenue": float(d["revenue"] or 0.0),
                        "profit": float(d["profit"] or 0.0),
                    }
                    for d in by_day
                ],
                "by_product": by_product,
            }
        )


class MobileSaleProfitDetailView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(tags=["Reports"])
    def get(self, request, pk):
        ctx = resolve_mobile_context(request)
        qs = Sale.objects.filter(id=pk, organization=ctx.organization)
        if ctx.branch and ctx.role != "owner":
            qs = qs.filter(branch=ctx.branch)
        sale = qs.first()
        if not sale:
            return Response({"detail": "Sale not found."}, status=status.HTTP_404_NOT_FOUND)

        items = sale.salesitem_set.select_related("inventory__product").all()
        breakdown = [
            {
                "product_name": item.inventory.product.product_name if item.inventory else None,
                "quantity": item.quantity,
                "revenue": float(item.total or 0.0),
                "cost": float(item.cost_total or 0.0),
                "profit": float(item.get_profit),
            }
            for item in items
        ]
        return Response(
            {
                "sale_id": str(sale.id),
                "transaction_id": sale.transaction_id,
                "final_total_price": float(sale.final_total_price or 0.0),
                "total_profit": float(sale.total_profit or 0.0),
                "items": breakdown,
            }
        )


class MobileCountSheetView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ("count",)

    @extend_schema(tags=["Inventory & Audit"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        if not ctx.branch:
            return Response({"detail": "No active branch selected."}, status=status.HTTP_400_BAD_REQUEST)

        product_name = (request.query_params.get("product") or "").strip() or None
        stats = InventoryService.get_variance_statistics(
            organization=ctx.organization,
            branch=ctx.branch,
            product_name=product_name,
        )
        items = [
            {
                "inventory_id": str(row["item"].id),
                "product_name": row["item"].product.product_name,
                "product_code": row["item"].product.product_code,
                "expected_quantity": row["item"].store_quantity,
                "reserved_in_open_sales": max(
                    0, (row["item"].quantity or 0) - row["item"].store_quantity
                ),
                "count": row["item"].count,
                "variance": row["variance"],
                "variance_pct": round(float(row["variance_pct"]), 2)
                if row["variance_pct"] is not None
                else None,
                "variance_status": row["variance_status"],
            }
            for row in stats["inventory"]
        ]
        return Response(
            {
                "total_items_counted": stats["total_items"],
                "total_inventory_items": stats["total_inventory_items"],
                "items_with_variance": stats["items_with_variance"],
                "total_variance_qty": stats["total_variance_qty"],
                "items": items,
            }
        )


class MobileCountBulkView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ("count",)

    @extend_schema(request=BulkCountInputSerializer, tags=["Inventory & Audit"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        if not ctx.branch:
            return Response({"detail": "No active branch selected."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = BulkCountInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        updated = []
        errors = []
        for entry in serializer.validated_data["items"]:
            inv = Inventory.objects.filter(
                id=entry["inventory_id"],
                organization=ctx.organization,
                branch=ctx.branch,
            ).select_related("product").first()
            if not inv:
                errors.append(f"Inventory {entry['inventory_id']} not found in active branch.")
                continue
            counted = entry["counted_quantity"]
            inv.count = counted
            inv.variance = counted - inv.store_quantity
            inv.save(update_fields=["count", "variance", "last_updated"])
            updated.append(
                {
                    "inventory_id": str(inv.id),
                    "product_name": inv.product.product_name,
                    "count": inv.count,
                    "variance": inv.variance,
                }
            )

        if updated:
            ActivityLog.objects.create(
                organization=ctx.organization,
                branch=ctx.branch,
                staff=request.user,
                activity=f"Bulk stock count recorded for {len(updated)} item(s) via mobile API",
            )
        return Response({"updated_count": len(updated), "updated": updated, "errors": errors})

