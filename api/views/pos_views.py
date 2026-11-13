import uuid

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.context import resolve_mobile_context
from api.pagination import paginate_queryset
from api.permissions import MOBILE_DEFAULT_PERMISSIONS
from api.serializers.pos import (
    CatalogInventorySerializer,
    CheckoutSerializer,
    OfflineSyncSerializer,
    OpenSaleCreateSerializer,
    SaleSerializer,
)
from ims.models import ErrorTicket, Inventory, OfflineSaleTemp, Sale, SalesItem


def _complete_sale_from_items(
    *,
    organization,
    branch,
    staff,
    items,
    method="Cash",
    discount=0.0,
    target_sale=None,
    transaction_id=None,
    temp_id=None,
):
    """
    Atomically validate stock, lock inventory rows, create/complete Sale + SalesItems,
    decrement inventory, and optionally record OfflineSaleTemp idempotency.
    """
    with transaction.atomic():
        if target_sale is not None:
            target_sale = (
                Sale.objects.select_for_update()
                .filter(id=target_sale.id, organization=organization, branch=branch)
                .first()
            )
            if target_sale is None:
                return None, Response({"detail": "Open sale not found."}, status=status.HTTP_404_NOT_FOUND)
            if target_sale.completed or target_sale.cancelled:
                state = "cancelled" if target_sale.cancelled else "completed"
                if temp_id:
                    ErrorTicket.objects.create(
                        organization=organization,
                        branch=branch,
                        staff=staff,
                        title="Offline Sync Conflict: Sale already closed",
                        description=(
                            f"Offline checkout (Temp ID: {temp_id}, method: {method}) targeted sale "
                            f"{target_sale.id}, which was already {state}."
                        ),
                        status="Pending",
                    )
                return None, Response(
                    {"detail": f"This sale was already {state}."},
                    status=status.HTTP_409_CONFLICT,
                )

        validated_items = []
        gross_total = 0.0
        total_cost = 0.0

        for entry in items:
            inv_id = entry["inventory_id"]
            qty = int(entry["quantity"])
            if qty <= 0:
                continue

            inventory = (
                Inventory.objects.select_for_update()
                .select_related("product")
                .filter(id=inv_id, organization=organization, branch=branch)
                .first()
            )
            if not inventory:
                return None, Response(
                    {"detail": f"Inventory item {inv_id} not found in active branch."},
                    status=status.HTTP_409_CONFLICT,
                )

            if inventory.quantity < qty:
                if temp_id:
                    ErrorTicket.objects.create(
                        organization=organization,
                        branch=branch,
                        staff=staff,
                        title=f"Offline Sync Shortage: {inventory.product.product_name}",
                        description=(
                            f"Offline checkout (Temp ID: {temp_id}) requested {qty} units of "
                            f"'{inventory.product.product_name}', but only {inventory.quantity} were available."
                        ),
                        status="Pending",
                    )
                return None, Response(
                    {
                        "detail": (
                            f"Insufficient stock for '{inventory.product.product_name}'. "
                            f"Available: {inventory.quantity}, requested: {qty}."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            line_total = float(inventory.sale_price or 0.0) * qty
            line_cost = float(inventory.cost_price or 0.0) * qty
            gross_total += line_total
            total_cost += line_cost
            validated_items.append(
                {
                    "inventory": inventory,
                    "quantity": qty,
                    "total": line_total,
                    "cost_total": line_cost,
                }
            )

        if not validated_items:
            return None, Response(
                {"detail": "At least one valid cart item is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        discount_val = max(0.0, min(float(discount or 0.0), gross_total))
        final_total = max(0.0, gross_total - discount_val)
        total_profit = final_total - total_cost
        tx_id = transaction_id or f"POS-{uuid.uuid4().hex[:10].upper()}"

        if target_sale is not None:
            sale = target_sale
            sale.method = method
            sale.discount = discount_val
            sale.final_total_price = final_total
            sale.total_profit = total_profit
            sale.transaction_id = tx_id
            sale.completed = True
            sale.date_updated = timezone.now()
            sale.save()
            sale.salesitem_set.all().delete()
        else:
            sale = Sale.objects.create(
                organization=organization,
                branch=branch,
                staff=staff,
                method=method,
                discount=discount_val,
                final_total_price=final_total,
                total_profit=total_profit,
                transaction_id=tx_id,
                completed=True,
            )

        for v_item in validated_items:
            inv = v_item["inventory"]
            qty = v_item["quantity"]
            SalesItem.objects.create(
                organization=organization,
                branch=branch,
                inventory=inv,
                sale=sale,
                quantity=qty,
                total=v_item["total"],
                cost_total=v_item["cost_total"],
            )
            inv.quantity = max(0, inv.quantity - qty)
            inv.quantity_available = max(0, inv.quantity_available - qty)
            inv.sold = (inv.sold or 0) + qty
            inv.status = "Restocking" if inv.quantity_available == 0 else "Available"
            inv.save(update_fields=["quantity", "quantity_available", "sold", "status"])

        if temp_id:
            OfflineSaleTemp.objects.create(
                temp_id=temp_id,
                sale=sale,
            )

        return sale, None


class MobilePOSCatalogView(APIView):
    permission_classes = MOBILE_DEFAULT_PERMISSIONS

    @extend_schema(tags=["POS"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        if not ctx.branch:
            return Response({"detail": "No active branch selected."}, status=status.HTTP_400_BAD_REQUEST)

        qs = (
            Inventory.objects.filter(organization=ctx.organization, branch=ctx.branch)
            .select_related("product", "product__category")
            .order_by("product__product_name")
        )
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(product__product_name__icontains=search)
                | Q(product__product_code__icontains=search)
                | Q(product__brand__icontains=search)
            )
        category_id = request.query_params.get("category")
        if category_id:
            qs = qs.filter(product__category_id=category_id)
        if request.query_params.get("in_stock") == "true":
            qs = qs.filter(quantity_available__gt=0)

        return Response(CatalogInventorySerializer(qs, many=True).data)


class MobilePOSOpenSalesView(APIView):
    permission_classes = MOBILE_DEFAULT_PERMISSIONS

    @extend_schema(tags=["POS"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        if not ctx.branch:
            return Response({"detail": "No active branch selected."}, status=status.HTTP_400_BAD_REQUEST)

        qs = (
            Sale.objects.filter(
                organization=ctx.organization,
                branch=ctx.branch,
                completed=False,
                cancelled=False,
            )
            .prefetch_related("salesitem_set__inventory__product")
            .order_by("-date_added")
        )
        if ctx.role != "owner":
            qs = qs.filter(staff=request.user)
        return Response(SaleSerializer(qs, many=True).data)

    @extend_schema(request=OpenSaleCreateSerializer, tags=["POS"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        if not ctx.branch:
            return Response({"detail": "No active branch selected."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = OpenSaleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data.get("items", [])

        with transaction.atomic():
            sale = Sale.objects.create(
                organization=ctx.organization,
                branch=ctx.branch,
                staff=request.user,
                completed=False,
            )
            running_total = 0.0
            for item in items:
                inv = Inventory.objects.filter(
                    id=item["inventory_id"],
                    organization=ctx.organization,
                    branch=ctx.branch,
                ).first()
                if not inv:
                    return Response(
                        {"detail": f"Inventory item {item['inventory_id']} not found."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                line_total = float(inv.sale_price or 0.0) * item["quantity"]
                line_cost = float(inv.cost_price or 0.0) * item["quantity"]
                running_total += line_total
                SalesItem.objects.create(
                    organization=ctx.organization,
                    branch=ctx.branch,
                    inventory=inv,
                    sale=sale,
                    quantity=item["quantity"],
                    total=line_total,
                    cost_total=line_cost,
                )
            sale.final_total_price = running_total
            sale.save(update_fields=["final_total_price"])

        return Response(SaleSerializer(sale).data, status=status.HTTP_201_CREATED)


class MobilePOSCheckoutView(APIView):
    permission_classes = MOBILE_DEFAULT_PERMISSIONS

    @extend_schema(request=CheckoutSerializer, tags=["POS"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        if not ctx.branch:
            return Response({"detail": "No active branch selected."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        target_sale = None
        items = data.get("items") or []
        if data.get("sale_id"):
            target_sale = Sale.objects.filter(
                id=data["sale_id"],
                organization=ctx.organization,
                branch=ctx.branch,
            ).first()
            if not target_sale:
                return Response({"detail": "Open sale not found."}, status=status.HTTP_404_NOT_FOUND)
            if not items:
                items = [
                    {"inventory_id": si.inventory_id, "quantity": si.quantity}
                    for si in target_sale.salesitem_set.all()
                    if si.inventory_id
                ]

        sale, err_resp = _complete_sale_from_items(
            organization=ctx.organization,
            branch=ctx.branch,
            staff=request.user,
            items=items,
            method=data["method"],
            discount=data.get("discount", 0.0),
            target_sale=target_sale,
        )
        if err_resp is not None:
            return err_resp

        return Response(SaleSerializer(sale).data, status=status.HTTP_200_OK)


class MobilePOSSyncOfflineView(APIView):
    permission_classes = MOBILE_DEFAULT_PERMISSIONS

    @extend_schema(request=OfflineSyncSerializer, tags=["POS"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        if not ctx.branch:
            return Response({"detail": "No active branch selected."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = OfflineSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        temp_id = data["tempId"]

        existing = (
            OfflineSaleTemp.objects.filter(temp_id=temp_id)
            .select_related("sale")
            .first()
        )
        if existing:
            return Response(
                {
                    "idempotent": True,
                    "message": "Already synced (idempotent).",
                    "sale": SaleSerializer(existing.sale).data,
                },
                status=status.HTTP_200_OK,
            )

        target_sale = None
        if data.get("server_sale_id"):
            target_sale = Sale.objects.filter(
                id=data["server_sale_id"],
                organization=ctx.organization,
                branch=ctx.branch,
            ).first()

        sale, err_resp = _complete_sale_from_items(
            organization=ctx.organization,
            branch=ctx.branch,
            staff=request.user,
            items=data["items"],
            method=data["method"],
            discount=data.get("discount", 0.0),
            target_sale=target_sale,
            transaction_id=temp_id,
            temp_id=temp_id,
        )
        if err_resp is not None:
            return err_resp

        return Response(
            {
                "idempotent": False,
                "message": "Offline sale synced successfully.",
                "sale": SaleSerializer(sale).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MobileSaleListView(APIView):
    permission_classes = MOBILE_DEFAULT_PERMISSIONS

    @extend_schema(tags=["Sales"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        qs = (
            Sale.objects.filter(organization=ctx.organization, completed=True, cancelled=False)
            .select_related("staff", "branch")
            .prefetch_related("salesitem_set__inventory__product")
            .order_by("-date_added")
        )
        if ctx.branch:
            qs = qs.filter(branch=ctx.branch)
        if ctx.role != "owner":
            qs = qs.filter(staff=request.user)

        method = request.query_params.get("method")
        if method:
            qs = qs.filter(method=method)

        return paginate_queryset(request, qs, SaleSerializer)


class MobileSaleDetailView(APIView):
    permission_classes = MOBILE_DEFAULT_PERMISSIONS

    @extend_schema(tags=["Sales"])
    def get(self, request, pk):
        ctx = resolve_mobile_context(request)
        qs = Sale.objects.filter(id=pk, organization=ctx.organization).select_related(
            "staff", "branch"
        ).prefetch_related("salesitem_set__inventory__product")
        if ctx.branch:
            qs = qs.filter(branch=ctx.branch)
        if ctx.role != "owner":
            qs = qs.filter(staff=request.user)

        sale = qs.first()
        if not sale:
            return Response({"detail": "Sale not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(SaleSerializer(sale).data)

