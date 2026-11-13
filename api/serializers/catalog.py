from rest_framework import serializers

from ims.models import Category, Inventory, Product


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "category_name", "branch_id", "last_updated", "date_created"]
        read_only_fields = ["id", "branch_id", "last_updated", "date_created"]


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.category_name", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "product_name",
            "category",
            "category_name",
            "brand",
            "product_code",
            "batch_no",
            "unit",
            "profit",
            "supplier_emails",
            "branch_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "branch_id", "created_at", "updated_at"]


class InventoryDetailSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.product_name", read_only=True)
    product_code = serializers.CharField(source="product.product_code", read_only=True)
    category_name = serializers.CharField(source="product.category.category_name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = Inventory
        fields = [
            "id",
            "product",
            "product_name",
            "product_code",
            "category_name",
            "branch_id",
            "branch_name",
            "quantity",
            "quantity_available",
            "reorder_level",
            "cost_price",
            "sale_price",
            "quantity_restocked",
            "count",
            "sold",
            "variance",
            "status",
            "last_updated",
            "date_created",
        ]
        read_only_fields = [
            "id",
            "branch_id",
            "branch_name",
            "quantity_restocked",
            "count",
            "sold",
            "variance",
            "last_updated",
            "date_created",
        ]


class RestockInputSerializer(serializers.Serializer):
    quantity_added = serializers.IntegerField(min_value=1)
    cost_price = serializers.FloatField(required=False, min_value=0.0)
    sale_price = serializers.FloatField(required=False, min_value=0.0)
    reorder_level = serializers.IntegerField(required=False, min_value=0)


class StockCountInputSerializer(serializers.Serializer):
    counted_quantity = serializers.IntegerField(min_value=0)

