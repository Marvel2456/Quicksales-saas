from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
from unfold.admin import ModelAdmin
from subscriptions.services.gateways import (
    BachsGateway,
    get_active_gateway_name,
    validate_positive_amount,
)
from .models import (
    Buyer, StoreListing, ProductListing,
    StoreDiscount, StoreDiscountRedemption,
    OnlineOrder, OnlineOrderItem,
    ServiceListing, ServiceEnrollment,
    StoreBankAccount, StorePayout,
)


@admin.register(Buyer)
class BuyerAdmin(ModelAdmin):
    list_display = ('email', 'first_name', 'last_name', 'phone_number', 'is_active', 'is_verified', 'created_at')
    search_fields = ('email', 'first_name', 'last_name', 'phone_number')
    list_filter = ('is_active', 'is_verified', 'created_at')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'


@admin.register(StoreListing)
class StoreListingAdmin(ModelAdmin):
    list_display = ('organization', 'branch', 'is_active', 'instagram_handle', 'whatsapp_number', 'created_at')
    search_fields = ('organization__name', 'tagline', 'instagram_handle')
    list_filter = ('is_active', 'created_at')
    raw_id_fields = ('organization', 'branch')


@admin.register(ProductListing)
class ProductListingAdmin(ModelAdmin):
    list_display = ('display_title', 'store', 'is_visible', 'featured', 'created_at')
    search_fields = ('custom_title', 'inventory__product__product_name', 'store__organization__name')
    list_filter = ('is_visible', 'featured', 'created_at')
    raw_id_fields = ('store', 'inventory')


@admin.register(StoreDiscount)
class StoreDiscountAdmin(ModelAdmin):
    list_display = ('code', 'organization', 'discount_type', 'value', 'scope', 'uses', 'max_uses', 'is_active', 'start_date', 'end_date')
    search_fields = ('code', 'label', 'organization__name')
    list_filter = ('discount_type', 'scope', 'is_active', 'created_at')
    raw_id_fields = ('organization', 'branch')


class OnlineOrderItemInline(admin.TabularInline):
    model = OnlineOrderItem
    extra = 0
    readonly_fields = ('product_name', 'unit_price', 'quantity', 'total_price')


@admin.register(OnlineOrder)
class OnlineOrderAdmin(ModelAdmin):
    list_display = ('order_number', 'organization', 'buyer_name', 'buyer_phone', 'status', 'total_amount', 'currency', 'created_at')
    search_fields = ('order_number', 'buyer_name', 'buyer_email', 'buyer_phone', 'organization__name')
    list_filter = ('status', 'currency', 'created_at')
    raw_id_fields = ('organization', 'branch', 'buyer', 'sale', 'discount')
    inlines = [OnlineOrderItemInline]
    date_hierarchy = 'created_at'


@admin.register(StoreDiscountRedemption)
class StoreDiscountRedemptionAdmin(ModelAdmin):
    list_display = ('discount', 'order', 'buyer', 'amount_saved', 'redeemed_at')
    search_fields = ('discount__code', 'order__order_number')
    list_filter = ('redeemed_at',)
    raw_id_fields = ('discount', 'order', 'buyer')


@admin.register(ServiceListing)
class ServiceListingAdmin(ModelAdmin):
    list_display = ('title', 'organization', 'price_ngn', 'price_usd', 'max_participants', 'is_active', 'created_at')
    search_fields = ('title', 'slug', 'organization__name')
    list_filter = ('is_active', 'created_at')
    raw_id_fields = ('organization', 'store')


@admin.register(ServiceEnrollment)
class ServiceEnrollmentAdmin(ModelAdmin):
    list_display = ('enrollment_number', 'service', 'attendee_name', 'attendee_email', 'country', 'currency', 'amount', 'settled_amount_ngn', 'payment_status', 'access_email_sent', 'created_at')
    search_fields = ('enrollment_number', 'payment_reference', 'attendee_name', 'attendee_email', 'country', 'service__title')
    list_filter = ('payment_status', 'currency', 'access_email_sent', 'created_at')
    raw_id_fields = ('organization', 'service', 'buyer')


@admin.register(StoreBankAccount)
class StoreBankAccountAdmin(ModelAdmin):
    list_display = ('organization', 'bank_name', 'account_number', 'account_name', 'bachs_destination_id', 'updated_at')
    search_fields = ('organization__name', 'bank_name', 'account_number', 'account_name')
    raw_id_fields = ('organization',)


@admin.register(StorePayout)
class StorePayoutAdmin(ModelAdmin):
    list_display = ('reference', 'organization', 'amount', 'currency', 'gateway', 'status', 'gateway_reference', 'created_at', 'processed_at')
    search_fields = ('reference', 'gateway_reference', 'organization__name', 'account_number', 'account_name')
    list_filter = ('status', 'gateway', 'currency', 'created_at')
    readonly_fields = ('reference', 'idempotency_key', 'gateway_reference', 'created_at', 'processed_at')
    raw_id_fields = ('organization', 'requested_by')
    actions = ['approve_and_disburse_via_gateway']

    @admin.action(description='Approve & Disburse Selected Payouts via Active Gateway')
    def approve_and_disburse_via_gateway(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, 'Only superusers can disburse payouts.', level=messages.ERROR)
            return

        active_gateway = get_active_gateway_name()
        disbursed = 0
        skipped = 0

        for payout_id in queryset.values_list('id', flat=True):
            try:
                with transaction.atomic():
                    payout = StorePayout.objects.select_for_update().get(id=payout_id)
                    if payout.status != 'pending':
                        skipped += 1
                        continue

                    validate_positive_amount(payout.amount, field_name='payout amount')
                    bank_account = StoreBankAccount.objects.filter(organization=payout.organization).first()
                    if not bank_account or bank_account.account_number != payout.account_number:
                        raise ValueError(
                            f'Bank account snapshot mismatch for payout {payout.reference}; manual review required.'
                        )

                    if active_gateway == 'bachs':
                        bachs = BachsGateway()
                        dest_id = bank_account.bachs_destination_id
                        if not dest_id:
                            if not bank_account.bank_code:
                                raise ValueError(f'Missing bank_code on {bank_account} for Bachs destination.')
                            dest = bachs.create_payout_destination(
                                currency=payout.currency,
                                account_number=bank_account.account_number,
                                bank_code=bank_account.bank_code,
                                name=bank_account.account_name,
                            )
                            dest_id = dest['destination_id']
                            bank_account.bachs_destination_id = dest_id
                            bank_account.save(update_fields=['bachs_destination_id', 'updated_at'])

                        res = bachs.create_payout(
                            destination_id=dest_id,
                            amount=payout.amount,
                            reference=payout.reference,
                            narration=f'Quicksales payout {payout.reference}',
                            idempotency_key=payout.idempotency_key or payout.reference,
                        )
                        payout.gateway = 'bachs'
                        payout.gateway_reference = res['payout_id']
                        payout.status = 'completed' if res['status'] in ('completed', 'succeeded', 'paid') else 'processing'
                        if payout.status == 'completed':
                            payout.processed_at = timezone.now()
                        payout.admin_notes = (
                            (payout.admin_notes + '\n' if payout.admin_notes else '')
                            + f'Disbursed via Bachs by {request.user.email} (ref={res["payout_id"]}).'
                        )
                        payout.save(update_fields=['gateway', 'gateway_reference', 'status', 'processed_at', 'admin_notes'])
                        disbursed += 1
                    else:
                        payout.gateway = active_gateway
                        payout.status = 'completed'
                        payout.processed_at = timezone.now()
                        payout.admin_notes = (
                            (payout.admin_notes + '\n' if payout.admin_notes else '')
                            + f'Approved for {active_gateway} by {request.user.email}.'
                        )
                        payout.save(update_fields=['gateway', 'status', 'processed_at', 'admin_notes'])
                        disbursed += 1
            except Exception as exc:
                self.message_user(request, f'Payout {payout_id} failed: {exc}', level=messages.ERROR)

        if disbursed:
            self.message_user(request, f'Disbursed {disbursed} payout(s) via {active_gateway}.', level=messages.SUCCESS)
        if skipped:
            self.message_user(request, f'Skipped {skipped} non-pending payout(s).', level=messages.WARNING)

