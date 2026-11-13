from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import ActivityLog
from api.context import resolve_mobile_context
from api.pagination import paginate_queryset
from api.permissions import HasRoleOrFeaturePermission, MOBILE_DEFAULT_PERMISSIONS
from api.serializers.catalog import (
    CategorySerializer,
    InventoryDetailSerializer,
    ProductSerializer,
    RestockInputSerializer,
    StockCountInputSerializer,
)
from ims.models import Category, Inventory, Product


class MobileCategoryListCreateView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ("categories",)

    @extend_schema(tags=["Categories"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        qs = Category.objects.filter(organization=ctx.organization).order_by("category_name")
        if ctx.branch:
            qs = qs.filter(branch=ctx.branch)
        return Response(CategorySerializer(qs, many=True).data)

    @extend_schema(request=CategorySerializer, tags=["Categories"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        if not ctx.branch:
            return Response({"detail": "No active branch selected."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data["category_name"].strip()
        if Category.objects.filter(
            organization=ctx.organization, branch=ctx.branch, category_name__iexact=name
        ).exists():
            return Response(
                {"category_name": ["Category already exists in this branch."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cat = Category.objects.create(
            organization=ctx.organization,
            branch=ctx.branch,
            category_name=name,
        )
        return Response(CategorySerializer(cat).data, status=status.HTTP_201_CREATED)


class MobileCategoryDetailView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ("categories",)

    def _get_obj(self, ctx, pk):
        qs = Category.objects.filter(id=pk, organization=ctx.organization)
        if ctx.branch and ctx.role != "owner":
            qs = qs.filter(branch=ctx.branch)
        return qs.first()

    @extend_schema(request=CategorySerializer, tags=["Categories"])
    def patch(self, request, pk):
        ctx = resolve_mobile_context(request)
        cat = self._get_obj(ctx, pk)
        if not cat:
            return Response({"detail": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = CategorySerializer(cat, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(tags=["Categories"])
    def delete(self, request, pk):
        ctx = resolve_mobile_context(request)
        cat = self._get_obj(ctx, pk)
        if not cat:
            return Response({"detail": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        cat.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MobileProductListCreateView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ("products",)

    @extend_schema(tags=["Products"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        qs = (
            Product.objects.filter(organization=ctx.organization)
            .select_related("category")
            .order_by("product_name")
        )
        if ctx.branch:
            qs = qs.filter(branch=ctx.branch)
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(product_name__icontains=search)
                | Q(product_code__icontains=search)
                | Q(brand__icontains=search)
            )
        return paginate_queryset(request, qs, ProductSerializer)

    @extend_schema(request=ProductSerializer, tags=["Products"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        if not ctx.branch:
            return Response({"detail": "No active branch selected."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = ProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = serializer.validated_data["category"]
        if category.organization_id != ctx.organization.id:
            return Response({"category": ["Invalid category for this organization."]}, status=status.HTTP_400_BAD_REQUEST)
        name = (serializer.validated_data.get("product_name") or "").strip()
        if name and Product.objects.filter(
            organization=ctx.organization, branch=ctx.branch, product_name__iexact=name
        ).exists():
            return Response(
                {"product_name": ["A product with this name already exists in this branch."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        product = serializer.save(organization=ctx.organization, branch=ctx.branch)
        return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)


class MobileProductDetailView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ("products",)

    def _get_obj(self, ctx, pk):
        qs = Product.objects.filter(id=pk, organization=ctx.organization).select_related("category")
        if ctx.branch and ctx.role != "owner":
            qs = qs.filter(branch=ctx.branch)
        return qs.first()

    @extend_schema(tags=["Products"])
    def get(self, request, pk):
        ctx = resolve_mobile_context(request)
        product = self._get_obj(ctx, pk)
        if not product:
            return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ProductSerializer(product).data)

    @extend_schema(request=ProductSerializer, tags=["Products"])
    def patch(self, request, pk):
        ctx = resolve_mobile_context(request)
        product = self._get_obj(ctx, pk)
        if not product:
            return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ProductSerializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if "category" in serializer.validated_data:
            if serializer.validated_data["category"].organization_id != ctx.organization.id:
                return Response({"category": ["Invalid category."]}, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(tags=["Products"])
    def delete(self, request, pk):
        ctx = resolve_mobile_context(request)
        product = self._get_obj(ctx, pk)
        if not product:
            return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)
        product.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MobileInventoryListCreateView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ("inventory",)

    @extend_schema(tags=["Inventory"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        qs = (
            Inventory.objects.filter(organization=ctx.organization)
            .select_related("product", "product__category", "branch")
            .order_by("product__product_name")
        )
        if ctx.branch:
            qs = qs.filter(branch=ctx.branch)
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(product__product_name__icontains=search)
                | Q(product__product_code__icontains=search)
            )
        return paginate_queryset(request, qs, InventoryDetailSerializer)

    @extend_schema(request=InventoryDetailSerializer, tags=["Inventory"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        if not ctx.branch:
            return Response({"detail": "No active branch selected."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = InventoryDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.validated_data["product"]
        if product.organization_id != ctx.organization.id:
            return Response({"product": ["Invalid product for this organization."]}, status=status.HTTP_400_BAD_REQUEST)
        if Inventory.objects.filter(
            organization=ctx.organization, branch=ctx.branch, product=product
        ).exists():
            return Response(
                {"product": ["Inventory record for this product already exists in this branch."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qty = serializer.validated_data.get("quantity", 0)
        qty_avail = serializer.validated_data.get("quantity_available", qty)
        inv = serializer.save(
            organization=ctx.organization,
            branch=ctx.branch,
            quantity_available=qty_avail,
            status="Restocking" if qty_avail <= 0 else "Available",
        )
        return Response(InventoryDetailSerializer(inv).data, status=status.HTTP_201_CREATED)


class MobileInventoryDetailView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ("inventory",)

    def _get_obj(self, ctx, pk):
        qs = Inventory.objects.filter(id=pk, organization=ctx.organization).select_related(
            "product", "product__category", "branch"
        )
        if ctx.branch and ctx.role != "owner":
            qs = qs.filter(branch=ctx.branch)
        return qs.first()

    @extend_schema(tags=["Inventory"])
    def get(self, request, pk):
        ctx = resolve_mobile_context(request)
        inv = self._get_obj(ctx, pk)
        if not inv:
            return Response({"detail": "Inventory item not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(InventoryDetailSerializer(inv).data)

    @extend_schema(request=InventoryDetailSerializer, tags=["Inventory"])
    def patch(self, request, pk):
        ctx = resolve_mobile_context(request)
        inv = self._get_obj(ctx, pk)
        if not inv:
            return Response({"detail": "Inventory item not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = InventoryDetailSerializer(inv, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(InventoryDetailSerializer(inv).data)


class MobileInventoryRestockView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ("inventory",)

    @extend_schema(request=RestockInputSerializer, tags=["Inventory"])
    def post(self, request, pk):
        ctx = resolve_mobile_context(request)
        qs = Inventory.objects.filter(id=pk, organization=ctx.organization).select_related("product", "branch")
        if ctx.branch and ctx.role != "owner":
            qs = qs.filter(branch=ctx.branch)
        inv = qs.first()
        if not inv:
            return Response({"detail": "Inventory item not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = RestockInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        qty_added = data["quantity_added"]

        inv.quantity = (inv.quantity or 0) + qty_added
        inv.quantity_available = (inv.quantity_available or 0) + qty_added
        inv.quantity_restocked = qty_added
        if "cost_price" in data:
            inv.cost_price = data["cost_price"]
        if "sale_price" in data:
            inv.sale_price = data["sale_price"]
        if "reorder_level" in data:
            inv.reorder_level = data["reorder_level"]
        inv.status = "Available" if inv.quantity_available > 0 else "Restocking"
        inv.save()

        ActivityLog.objects.create(
            organization=ctx.organization,
            branch=inv.branch,
            staff=request.user,
            activity=f"Restocked {qty_added} units of {inv.product.product_name} via mobile API",
        )
        return Response(InventoryDetailSerializer(inv).data)


class MobileInventoryCountView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner", "manager")
    required_feature_permissions = ("count",)

    @extend_schema(request=StockCountInputSerializer, tags=["Inventory"])
    def post(self, request, pk):
        ctx = resolve_mobile_context(request)
        qs = Inventory.objects.filter(id=pk, organization=ctx.organization).select_related("product", "branch")
        if ctx.branch and ctx.role != "owner":
            qs = qs.filter(branch=ctx.branch)
        inv = qs.first()
        if not inv:
            return Response({"detail": "Inventory item not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = StockCountInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        counted = serializer.validated_data["counted_quantity"]

        inv.count = counted
        inv.variance = counted - inv.store_quantity
        inv.save(update_fields=["count", "variance", "last_updated"])

        ActivityLog.objects.create(
            organization=ctx.organization,
            branch=inv.branch,
            staff=request.user,
            activity=(
                f"Stock count recorded for {inv.product.product_name}: "
                f"counted={counted}, variance={inv.variance}"
            ),
        )
        return Response(InventoryDetailSerializer(inv).data)

