from rest_framework import serializers

from ims.models import Inventory, Sale, SalesItem


class CatalogInventorySerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(source="product.id", read_only=True)
    product_name = serializers.CharField(source="product.product_name", read_only=True)
    product_code = serializers.CharField(source="product.product_code", read_only=True)
    brand = serializers.CharField(source="product.brand", read_only=True)
    unit = serializers.CharField(source="product.unit", read_only=True)
    category_id = serializers.UUIDField(source="product.category_id", read_only=True)
    category_name = serializers.CharField(
        source="product.category.category_name", read_only=True, default=None
    )

    class Meta:
        model = Inventory
        fields = [
            "id",
            "product_id",
            "product_name",
            "product_code",
            "brand",
            "unit",
            "category_id",
            "category_name",
            "quantity",
            "quantity_available",
            "reorder_level",
            "cost_price",
            "sale_price",
            "status",
        ]


class SaleItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source="inventory.product.product_name", read_only=True, default=None
    )
    unit_price = serializers.SerializerMethodField()

    class Meta:
        model = SalesItem
        fields = [
            "id",
            "inventory_id",
            "product_name",
            "quantity",
            "unit_price",
            "total",
            "cost_total",
            "last_updated",
        ]

    def get_unit_price(self, obj):
        if obj.quantity:
            return round(float(obj.total or 0) / obj.quantity, 2)
        return float(obj.inventory.sale_price or 0) if obj.inventory_id else 0.0


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(source="salesitem_set", many=True, read_only=True)
    staff_name = serializers.SerializerMethodField()
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id",
            "transaction_id",
            "branch_id",
            "branch_name",
            "staff_id",
            "staff_name",
            "method",
            "discount",
            "final_total_price",
            "total_profit",
            "completed",
            "cancelled",
            "date_added",
            "items",
        ]

    def get_staff_name(self, obj):
        if not obj.staff:
            return None
        full_name = f"{obj.staff.first_name} {obj.staff.last_name}".strip()
        return full_name or obj.staff.email


class CartLineInputSerializer(serializers.Serializer):
    inventory_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class OpenSaleCreateSerializer(serializers.Serializer):
    items = CartLineInputSerializer(many=True, required=False, default=list)


class CheckoutSerializer(serializers.Serializer):
    sale_id = serializers.UUIDField(required=False, allow_null=True)
    method = serializers.ChoiceField(choices=["Cash", "Transfer", "POS"], default="Cash")
    discount = serializers.FloatField(required=False, default=0.0, min_value=0.0)
    items = CartLineInputSerializer(many=True, required=False, default=list)


class OfflineSyncSerializer(serializers.Serializer):
    tempId = serializers.CharField(max_length=100)
    server_sale_id = serializers.UUIDField(required=False, allow_null=True)
    method = serializers.ChoiceField(choices=["Cash", "Transfer", "POS"], default="Cash")
    discount = serializers.FloatField(required=False, default=0.0, min_value=0.0)
    items = CartLineInputSerializer(many=True)

