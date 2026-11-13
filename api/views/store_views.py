from decimal import Decimal
import secrets

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Branch
from api.context import resolve_mobile_context
from api.pagination import paginate_queryset
from api.permissions import (
    HasRoleOrFeaturePermission,
    IsOwnerOnly,
    MOBILE_DEFAULT_PERMISSIONS,
)
from api.serializers.store import (
    OnlineOrderActionSerializer,
    OnlineOrderSerializer,
    PayoutRequestInputSerializer,
    ProductListingSerializer,
    ServiceEnrollmentSerializer,
    ServiceListingSerializer,
    StoreBankAccountSerializer,
    StoreDiscountSerializer,
    StorePayoutSerializer,
    StoreSettingsSerializer,
)
from ims.models import Inventory
from store.models import (
    OnlineOrder,
    ProductListing,
    ServiceEnrollment,
    ServiceListing,
    StoreBankAccount,
    StoreDiscount,
    StoreListing,
    StorePayout,
)
from store.vendor_views import calculate_organization_balances, request_organization_payout
from store.views import complete_order_sale


class MobileStoreSettingsView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(tags=["Store"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        store, _ = StoreListing.objects.get_or_create(organization=ctx.organization)
        return Response(StoreSettingsSerializer(store).data)

    @extend_schema(request=StoreSettingsSerializer, tags=["Store"])
    def patch(self, request):
        ctx = resolve_mobile_context(request)
        store, _ = StoreListing.objects.get_or_create(organization=ctx.organization)
        serializer = StoreSettingsSerializer(store, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if "branch" in serializer.validated_data and serializer.validated_data["branch"]:
            if serializer.validated_data["branch"].organization_id != ctx.organization.id:
                return Response(
                    {"branch": ["Branch does not belong to this organization."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        serializer.save()
        return Response(serializer.data)


class MobileProductListingListCreateView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(tags=["Store"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        store, _ = StoreListing.objects.get_or_create(organization=ctx.organization)
        qs = ProductListing.objects.filter(store=store).select_related("inventory__product")
        return Response(ProductListingSerializer(qs, many=True).data)

    @extend_schema(request=ProductListingSerializer, tags=["Store"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        store, _ = StoreListing.objects.get_or_create(organization=ctx.organization)
        serializer = ProductListingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inv = serializer.validated_data["inventory"]
        if inv.organization_id != ctx.organization.id:
            return Response(
                {"inventory": ["Inventory item does not belong to this organization."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if ProductListing.objects.filter(store=store, inventory=inv).exists():
            return Response(
                {"inventory": ["This inventory item is already listed on the storefront."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        listing = serializer.save(store=store)
        return Response(ProductListingSerializer(listing).data, status=status.HTTP_201_CREATED)


class MobileProductListingDetailView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    def _get_listing(self, ctx, pk):
        return (
            ProductListing.objects.filter(id=pk, store__organization=ctx.organization)
            .select_related("inventory__product")
            .first()
        )

    @extend_schema(request=ProductListingSerializer, tags=["Store"])
    def patch(self, request, pk):
        ctx = resolve_mobile_context(request)
        listing = self._get_listing(ctx, pk)
        if not listing:
            return Response({"detail": "Product listing not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ProductListingSerializer(listing, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(tags=["Store"])
    def delete(self, request, pk):
        ctx = resolve_mobile_context(request)
        listing = self._get_listing(ctx, pk)
        if not listing:
            return Response({"detail": "Product listing not found."}, status=status.HTTP_404_NOT_FOUND)
        listing.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MobileOnlineOrderListView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(tags=["Store Orders"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        qs = (
            OnlineOrder.objects.filter(organization=ctx.organization)
            .prefetch_related("items")
            .order_by("-created_at")
        )
        if ctx.branch and ctx.role != "owner":
            qs = qs.filter(branch=ctx.branch)
        order_status = request.query_params.get("status")
        if order_status:
            qs = qs.filter(status=order_status)
        return paginate_queryset(request, qs, OnlineOrderSerializer)


class MobileOnlineOrderDetailView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(tags=["Store Orders"])
    def get(self, request, pk):
        ctx = resolve_mobile_context(request)
        order = (
            OnlineOrder.objects.filter(id=pk, organization=ctx.organization)
            .prefetch_related("items")
            .first()
        )
        if not order:
            return Response({"detail": "Online order not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(OnlineOrderSerializer(order).data)


class MobileOnlineOrderActionView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(request=OnlineOrderActionSerializer, tags=["Store Orders"])
    def post(self, request, pk):
        ctx = resolve_mobile_context(request)
        order = (
            OnlineOrder.objects.filter(id=pk, organization=ctx.organization)
            .prefetch_related("items__inventory")
            .first()
        )
        if not order:
            return Response({"detail": "Online order not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = OnlineOrderActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        action = data["action"]

        if action == "confirm":
            if order.status != "pending":
                return Response(
                    {"detail": f"Order is already {order.status}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            branch = order.branch or ctx.organization.default_branch or Branch.objects.filter(
                organization=ctx.organization
            ).first()
            if not branch:
                return Response(
                    {"detail": "No branch assigned to fulfill this order."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            for item in order.items.all():
                inv = item.inventory
                avail = (
                    inv.store_quantity
                    if (inv and hasattr(inv, "store_quantity"))
                    else (inv.quantity if inv else 0)
                )
                if not inv or avail < item.quantity:
                    return Response(
                        {"detail": f"Insufficient stock for '{item.product_name}'. Available: {avail}."},
                        status=status.HTTP_409_CONFLICT,
                    )
            complete_order_sale(order, staff=request.user)
            order.refresh_from_db()
            return Response(OnlineOrderSerializer(order).data)

        if action == "dispatch":
            order.courier_name = data.get("courier_name", "")
            order.tracking_number = data.get("tracking_number", "")
            order.dispatch_note = data.get("dispatch_note", "")
            order.dispatched_at = timezone.now()
            order.status = "dispatched"
            order.save(
                update_fields=[
                    "courier_name",
                    "tracking_number",
                    "dispatch_note",
                    "dispatched_at",
                    "status",
                    "updated_at",
                ]
            )
            return Response(OnlineOrderSerializer(order).data)

        if action == "deliver":
            order.delivered_at = timezone.now()
            order.status = "delivered"
            order.save(update_fields=["delivered_at", "status", "updated_at"])
            return Response(OnlineOrderSerializer(order).data)

        # cancel
        if order.status in ("delivered", "cancelled"):
            return Response(
                {"detail": f"Cannot cancel an order that is already {order.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = "cancelled"
        order.cancelled_at = timezone.now()
        order.cancelled_reason = data.get("cancelled_reason", "")
        order.save(update_fields=["status", "cancelled_at", "cancelled_reason", "updated_at"])
        return Response(OnlineOrderSerializer(order).data)


class MobileServiceListCreateView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(tags=["Services & Classes"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        qs = ServiceListing.objects.filter(organization=ctx.organization).order_by("-created_at")
        return Response(ServiceListingSerializer(qs, many=True).data)

    @extend_schema(request=ServiceListingSerializer, tags=["Services & Classes"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        store, _ = StoreListing.objects.get_or_create(organization=ctx.organization)
        serializer = ServiceListingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = serializer.save(organization=ctx.organization, store=store)
        return Response(ServiceListingSerializer(service).data, status=status.HTTP_201_CREATED)


class MobileServiceDetailView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    def _get_service(self, ctx, pk):
        return ServiceListing.objects.filter(id=pk, organization=ctx.organization).first()

    @extend_schema(tags=["Services & Classes"])
    def get(self, request, pk):
        ctx = resolve_mobile_context(request)
        service = self._get_service(ctx, pk)
        if not service:
            return Response({"detail": "Service not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ServiceListingSerializer(service).data)

    @extend_schema(request=ServiceListingSerializer, tags=["Services & Classes"])
    def patch(self, request, pk):
        ctx = resolve_mobile_context(request)
        service = self._get_service(ctx, pk)
        if not service:
            return Response({"detail": "Service not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ServiceListingSerializer(service, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(tags=["Services & Classes"])
    def delete(self, request, pk):
        ctx = resolve_mobile_context(request)
        service = self._get_service(ctx, pk)
        if not service:
            return Response({"detail": "Service not found."}, status=status.HTTP_404_NOT_FOUND)
        service.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MobileServiceEnrollmentListView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(tags=["Services & Classes"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        qs = (
            ServiceEnrollment.objects.filter(organization=ctx.organization)
            .select_related("service")
            .order_by("-created_at")
        )
        service_id = request.query_params.get("service")
        if service_id:
            qs = qs.filter(service_id=service_id)
        pay_status = request.query_params.get("payment_status")
        if pay_status:
            qs = qs.filter(payment_status=pay_status)
        return paginate_queryset(request, qs, ServiceEnrollmentSerializer)


class MobileWalletView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, IsOwnerOnly]

    @extend_schema(tags=["Wallet & Payouts"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        balances = calculate_organization_balances(ctx.organization)
        bank_account, _ = StoreBankAccount.objects.get_or_create(
            organization=ctx.organization,
            defaults={"bank_name": "", "account_number": "", "account_name": ""},
        )
        payouts = StorePayout.objects.filter(organization=ctx.organization).order_by("-created_at")[:25]
        return Response(
            {
                "total_gross_revenue": float(balances["total_gross_revenue"]),
                "completed_payouts": float(balances["completed_payouts"]),
                "pending_payouts": float(balances["pending_payouts"]),
                "available_balance": float(balances["available_balance"]),
                "bank_account": StoreBankAccountSerializer(bank_account).data,
                "recent_payouts": StorePayoutSerializer(payouts, many=True).data,
            }
        )


class MobileBankAccountUpdateView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, IsOwnerOnly]

    @extend_schema(request=StoreBankAccountSerializer, tags=["Wallet & Payouts"])
    def patch(self, request):
        ctx = resolve_mobile_context(request)
        bank_account, _ = StoreBankAccount.objects.get_or_create(
            organization=ctx.organization,
            defaults={"bank_name": "", "account_number": "", "account_name": ""},
        )
        serializer = StoreBankAccountSerializer(bank_account, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class MobilePayoutListCreateView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, IsOwnerOnly]

    @extend_schema(tags=["Wallet & Payouts"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        payouts = StorePayout.objects.filter(organization=ctx.organization).order_by("-created_at")
        return paginate_queryset(request, payouts, StorePayoutSerializer)

    @extend_schema(request=PayoutRequestInputSerializer, tags=["Wallet & Payouts"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        serializer = PayoutRequestInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        idem_key = (data.get("idempotency_key") or "").strip() or None
        existing = (
            StorePayout.objects.filter(
                organization=ctx.organization, idempotency_key=idem_key
            ).first()
            if idem_key
            else None
        )
        if existing:
            return Response(
                {
                    "idempotent": True,
                    "detail": "Payout already recorded (idempotent).",
                    "payout": StorePayoutSerializer(existing).data,
                },
                status=status.HTTP_200_OK,
            )

        success, msg, payout = request_organization_payout(
            ctx.organization,
            request.user,
            data["amount"],
            notes=data.get("notes", ""),
            idempotency_key=idem_key,
        )
        if not success:
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "idempotent": False,
                "detail": msg,
                "payout": StorePayoutSerializer(payout).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MobileStoreDiscountListCreateView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(tags=["Store"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        qs = StoreDiscount.objects.filter(organization=ctx.organization).order_by("-created_at")
        return Response(StoreDiscountSerializer(qs, many=True).data)

    @extend_schema(request=StoreDiscountSerializer, tags=["Store"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        store, _ = StoreListing.objects.get_or_create(organization=ctx.organization)
        serializer = StoreDiscountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = (serializer.validated_data.get("code") or "").strip().upper()
        if not code:
            code = f"QS-{secrets.token_hex(3).upper()}"
        if StoreDiscount.objects.filter(organization=ctx.organization, code=code).exists():
            return Response(
                {"code": [f"A discount with code '{code}' already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        discount = serializer.save(
            organization=ctx.organization,
            branch=store.get_active_branch(),
            code=code,
        )
        return Response(StoreDiscountSerializer(discount).data, status=status.HTTP_201_CREATED)


class MobileStoreDiscountDetailView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(request=StoreDiscountSerializer, tags=["Store"])
    def patch(self, request, pk):
        ctx = resolve_mobile_context(request)
        discount = StoreDiscount.objects.filter(id=pk, organization=ctx.organization).first()
        if not discount:
            return Response({"detail": "Discount not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = StoreDiscountSerializer(discount, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(tags=["Store"])
    def delete(self, request, pk):
        ctx = resolve_mobile_context(request)
        discount = StoreDiscount.objects.filter(id=pk, organization=ctx.organization).first()
        if not discount:
            return Response({"detail": "Discount not found."}, status=status.HTTP_404_NOT_FOUND)
        discount.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MobileStoreCustomersView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ()

    @extend_schema(tags=["Store"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        orders = (
            OnlineOrder.objects.filter(organization=ctx.organization)
            .select_related("buyer")
            .order_by("-created_at")
        )
        customers_map = {}
        for o in orders:
            email = (o.buyer_email or (o.buyer.email if o.buyer else "")).strip().lower()
            if not email:
                continue
            if email not in customers_map:
                customers_map[email] = {
                    "email": email,
                    "name": o.buyer_name or (o.buyer.get_full_name() if o.buyer else email),
                    "phone": o.buyer_phone or (o.buyer.phone_number if o.buyer else ""),
                    "shipping_address": o.shipping_address,
                    "orders_count": 0,
                    "completed_orders_count": 0,
                    "total_spent": Decimal("0.00"),
                    "last_order_date": o.created_at,
                }
            entry = customers_map[email]
            entry["orders_count"] += 1
            if o.payment_status == "paid":
                entry["completed_orders_count"] += 1
                entry["total_spent"] += o.total_amount or Decimal("0.00")

        results = sorted(
            [
                {**v, "total_spent": float(v["total_spent"])}
                for v in customers_map.values()
            ],
            key=lambda x: x["total_spent"],
            reverse=True,
        )
        return Response(results)

