from decimal import Decimal
from rest_framework import serializers

from store.models import (
    OnlineOrder,
    OnlineOrderItem,
    ProductListing,
    ServiceEnrollment,
    ServiceListing,
    StoreBankAccount,
    StoreDiscount,
    StoreListing,
    StorePayout,
)


class StoreSettingsSerializer(serializers.ModelSerializer):
    organization_slug = serializers.CharField(source="organization.slug", read_only=True)

    class Meta:
        model = StoreListing
        fields = [
            "id",
            "organization_slug",
            "branch",
            "is_active",
            "tagline",
            "announcement",
            "contact_email",
            "online_store_email",
            "contact_phone",
            "instagram_handle",
            "whatsapp_number",
            "primary_color",
            "updated_at",
        ]
        read_only_fields = ["id", "organization_slug", "updated_at"]


class ProductListingSerializer(serializers.ModelSerializer):
    display_title = serializers.CharField(read_only=True)
    display_price = serializers.FloatField(read_only=True)
    stock_quantity = serializers.IntegerField(read_only=True)
    product_name = serializers.CharField(
        source="inventory.product.product_name", read_only=True
    )

    class Meta:
        model = ProductListing
        fields = [
            "id",
            "inventory",
            "product_name",
            "display_title",
            "display_price",
            "stock_quantity",
            "is_visible",
            "featured",
            "custom_title",
            "custom_description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class OnlineOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OnlineOrderItem
        fields = [
            "id",
            "product_listing_id",
            "inventory_id",
            "product_name",
            "unit_price",
            "quantity",
            "total_price",
        ]


class OnlineOrderSerializer(serializers.ModelSerializer):
    items = OnlineOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = OnlineOrder
        fields = [
            "id",
            "order_number",
            "branch_id",
            "buyer_name",
            "buyer_email",
            "buyer_phone",
            "shipping_address",
            "customer_notes",
            "sale_id",
            "status",
            "payment_method",
            "payment_status",
            "payment_reference",
            "paid_at",
            "currency",
            "subtotal",
            "discount_amount",
            "total_amount",
            "courier_name",
            "tracking_number",
            "dispatch_note",
            "dispatched_at",
            "delivered_at",
            "cancelled_at",
            "cancelled_reason",
            "created_at",
            "items",
        ]


class OnlineOrderActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["confirm", "dispatch", "deliver", "cancel"])
    courier_name = serializers.CharField(required=False, allow_blank=True, default="")
    tracking_number = serializers.CharField(required=False, allow_blank=True, default="")
    dispatch_note = serializers.CharField(required=False, allow_blank=True, default="")
    cancelled_reason = serializers.CharField(required=False, allow_blank=True, default="")


class ServiceListingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceListing
        fields = [
            "id",
            "title",
            "slug",
            "description",
            "price_ngn",
            "price_usd",
            "usd_to_ngn_rate",
            "access_link",
            "access_instructions",
            "event_date",
            "max_participants",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]


class ServiceEnrollmentSerializer(serializers.ModelSerializer):
    service_title = serializers.CharField(source="service.title", read_only=True)

    class Meta:
        model = ServiceEnrollment
        fields = [
            "id",
            "enrollment_number",
            "service_id",
            "service_title",
            "attendee_name",
            "attendee_email",
            "attendee_phone",
            "country",
            "city_state",
            "currency",
            "amount",
            "settled_amount_ngn",
            "payment_status",
            "paid_at",
            "access_email_sent",
            "created_at",
        ]


class StoreBankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreBankAccount
        fields = ["id", "bank_name", "bank_code", "account_number", "account_name", "updated_at"]
        read_only_fields = ["id", "updated_at"]


class StorePayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = StorePayout
        fields = [
            "id",
            "reference",
            "idempotency_key",
            "amount",
            "currency",
            "bank_name",
            "account_number",
            "account_name",
            "status",
            "notes",
            "admin_notes",
            "created_at",
            "processed_at",
        ]


class PayoutRequestInputSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1.00"))
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True, allow_null=True)


class StoreDiscountSerializer(serializers.ModelSerializer):
    code = serializers.CharField(max_length=50, required=False, allow_blank=True)

    class Meta:
        model = StoreDiscount
        fields = [
            "id",
            "code",
            "label",
            "discount_type",
            "value",
            "scope",
            "max_uses",
            "uses",
            "start_date",
            "end_date",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "uses", "created_at"]


