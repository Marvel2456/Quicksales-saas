from django.contrib import admin
from django.utils.html import format_html, format_html_join
from unfold.admin import ModelAdmin
from .models import Plan, Subscription, Payment, Coupon, CouponRedemption, PaymentGatewayConfig
from .services.settlement import get_platform_settlement_summary
# Register your models here.


@admin.register(PaymentGatewayConfig)
class PaymentGatewayConfigAdmin(ModelAdmin):
    list_display = (
        'active_gateway',
        'minimum_withdrawal_ngn',
        'quicksales_settleable_summary',
        'customer_withdrawable_summary',
        'updated_at',
        'updated_by',
    )
    readonly_fields = ('updated_at', 'funds_settlement_breakdown')
    fields = ('active_gateway', 'minimum_withdrawal_ngn', 'updated_at', 'funds_settlement_breakdown')

    def has_add_permission(self, request):
        return not PaymentGatewayConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description='Quicksales Funds (Safe to Settle)')
    def quicksales_settleable_summary(self, obj):
        summary = get_platform_settlement_summary()
        parts = [f"{r['currency']} {r['safe_to_settle_ours']:,.2f}" for r in summary['rows']]
        return ' | '.join(parts)

    @admin.display(description='Customer Funds Held (Withdrawable)')
    def customer_withdrawable_summary(self, obj):
        summary = get_platform_settlement_summary()
        parts = [f"{r['currency']} {r['customer_withdrawable_held']:,.2f}" for r in summary['rows']]
        return ' | '.join(parts)

    @admin.display(description='Platform vs. Customer Funds Breakdown')
    def funds_settlement_breakdown(self, obj):
        summary = get_platform_settlement_summary()
        rows_html = format_html_join(
            '',
            '<tr>'
            '<td style="padding:8px 12px;font-weight:600;border-bottom:1px solid #e5e7eb;">{}</td>'
            '<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;color:#15803d;font-weight:700;">{:,.2f}</td>'
            '<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{:,.2f} / {:,.2f}</td>'
            '<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{:,.2f}</td>'
            '<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{:,.2f}</td>'
            '<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{:,.2f}</td>'
            '<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;color:#b45309;font-weight:700;">{:,.2f}</td>'
            '<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-weight:600;">{:,.2f}</td>'
            '</tr>',
            (
                (
                    r['currency'],
                    r['safe_to_settle_ours'],
                    r['platform_bachs'],
                    r['platform_squadco'],
                    r['customer_gross'],
                    r['customer_paid_out'],
                    r['customer_pending_payouts'],
                    r['customer_withdrawable_held'],
                    r['expected_gateway_balance'],
                )
                for r in summary['rows']
            ),
        )
        return format_html(
            '<div style="overflow-x:auto;margin-top:6px;">'
            '<p style="margin-bottom:8px;color:#4b5563;">'
            '<strong>Green = Quicksales Revenue (Safe to Settle).</strong> '
            '<strong>Amber = Customer/Vendor Store Funds Held (Reserved for Withdrawals — Do Not Settle).</strong>'
            '</p>'
            '<table style="border-collapse:collapse;width:100%;font-size:13px;border:1px solid #e5e7eb;">'
            '<thead><tr style="background:#f9fafb;text-align:left;">'
            '<th style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">Currency</th>'
            '<th style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">Ours (Safe to Settle)</th>'
            '<th style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">Ours: Bachs / SquadCo</th>'
            '<th style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">Customer Gross Sales</th>'
            '<th style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">Paid Out to Customers</th>'
            '<th style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">Pending Withdrawals</th>'
            '<th style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">Customer Funds Held</th>'
            '<th style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">Expected Gateway Balance</th>'
            '</tr></thead>'
            '<tbody>{}</tbody>'
            '</table></div>',
            rows_html,
        )


@admin.register(Plan)
class PlanAdmin(ModelAdmin):
    list_display = ('name', 'tier', 'size', 'billing_frequency', 'price', 'price_usd', 'has_online_store', 'disable_store', 'max_users', 'max_branches', 'max_products', 'created_at')
    search_fields = ('name', 'tier', 'size')
    list_filter = ('tier', 'size', 'billing_frequency', 'has_online_store')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    list_per_page = 10
    list_display_links = ('name',)  

    fields = (
        'name',
        'tier',
        'size',
        'billing_frequency',
        'price',
        'price_usd',
        'duration_in_days',
        'description',
        'has_online_store',
        'disable_store',
        'max_users',
        'max_branches',
        'max_products',
        'created_at',
        'updated_at',
    )

    readonly_fields = ('created_at', 'updated_at')  


@admin.register(Subscription)
class SubscriptionAdmin(ModelAdmin):
    list_display = ('organization', 'plan', 'start_date', 'end_date', 'is_active')
    search_fields = ('organization__name', 'plan__name')
    list_filter = ('is_active',)
    ordering = ('-start_date',)
    date_hierarchy = 'start_date'
    list_per_page = 10
    list_display_links = ('organization', 'plan')
    raw_id_fields = ('organization', 'plan')
    autocomplete_fields = ('organization', 'plan')


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = ('subscription', 'amount', 'currency', 'payment_method', 'payment_status')
    search_fields = ('subscription__organization__name', 'subscription__plan__name')
    list_filter = ('payment_status', 'currency')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    list_per_page = 10
    list_display_links = ('subscription', 'amount')
    raw_id_fields = ('subscription',)
    autocomplete_fields = ('subscription',)

@admin.register(Coupon)
class CouponAdmin(ModelAdmin):
    list_display = ('code', 'type', 'value', 'uses', 'max_uses', 'is_active', 'created_at')
    search_fields = ('code',)
    list_filter = ('type', 'is_active', 'created_at')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    list_per_page = 10
    list_display_links = ('code',)
    readonly_fields = ('created_at', 'updated_at', 'uses')
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('code', 'type', 'is_active')
        }),
        ('Discount Value', {
            'fields': ('value', 'duration_days'),
            'description': 'For percent: enter 10 for 10%. For fixed: enter amount in currency. For free_month: set duration_days to subscription length.',
        }),
        ('Usage Limits', {
            'fields': ('max_uses', 'uses'),
        }),
        ('Validity Period', {
            'fields': ('start_date', 'end_date'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(ModelAdmin):
    list_display = ('coupon', 'organization', 'subscription', 'used_at')
    search_fields = ('coupon__code', 'organization__name')
    list_filter = ('used_at', 'coupon__type')
    ordering = ('-used_at',)
    date_hierarchy = 'used_at'
    list_per_page = 10
    list_display_links = ('coupon', 'organization')
    raw_id_fields = ('coupon', 'organization', 'subscription')
    autocomplete_fields = ('coupon', 'organization', 'subscription')
    readonly_fields = ('used_at',)