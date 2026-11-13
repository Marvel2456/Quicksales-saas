from rest_framework import serializers

from ims.models import Invoice, InvoiceEditLog, InvoiceItem, InvoicePayment


class InvoiceItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source="inventory.product.product_name", read_only=True, default=None
    )

    class Meta:
        model = InvoiceItem
        fields = [
            "id",
            "inventory_id",
            "product_name",
            "quantity",
            "unit_price",
            "total",
        ]


class InvoicePaymentSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = InvoicePayment
        fields = [
            "id",
            "amount",
            "payment_method",
            "recorded_by_id",
            "recorded_by_name",
            "notes",
            "date_paid",
        ]

    def get_recorded_by_name(self, obj):
        if not obj.recorded_by:
            return None
        name = f"{obj.recorded_by.first_name} {obj.recorded_by.last_name}".strip()
        return name or obj.recorded_by.email


class InvoiceEditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceEditLog
        fields = ["id", "action", "summary", "user_id", "user_name", "timestamp"]

    def get_user_name(self, obj):
        if not obj.user:
            return None
        name = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return name or obj.user.email


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    payments = InvoicePaymentSerializer(many=True, read_only=True)
    edit_logs = InvoiceEditLogSerializer(many=True, read_only=True)
    balance_due = serializers.FloatField(read_only=True)
    payment_progress_percent = serializers.IntegerField(read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "branch_id",
            "branch_name",
            "created_by_id",
            "created_by_name",
            "customer_name",
            "customer_email",
            "customer_phone",
            "notes",
            "status",
            "payment_plan",
            "payment_method",
            "due_date",
            "total_amount",
            "amount_paid",
            "balance_due",
            "payment_progress_percent",
            "inventory_deducted",
            "date_created",
            "date_updated",
            "items",
            "payments",
            "edit_logs",
        ]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        name = f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
        return name or obj.created_by.email


class InvoiceLineInputSerializer(serializers.Serializer):
    inventory_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.FloatField(required=False, min_value=0.0)


class InvoiceCreateSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=255)
    customer_email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    customer_phone = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    payment_plan = serializers.ChoiceField(
        choices=["one_time", "installment"], default="one_time"
    )
    due_date = serializers.DateField(required=False, allow_null=True)
    items = InvoiceLineInputSerializer(many=True)


class InvoiceUpdateSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=255, required=False)
    customer_email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    customer_phone = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    payment_plan = serializers.ChoiceField(choices=["one_time", "installment"], required=False)
    due_date = serializers.DateField(required=False, allow_null=True)
    items = InvoiceLineInputSerializer(many=True, required=False)


class RecordPaymentSerializer(serializers.Serializer):
    amount = serializers.FloatField(min_value=0.01)
    payment_method = serializers.ChoiceField(choices=["Cash", "Transfer", "POS"], default="Cash")
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")

