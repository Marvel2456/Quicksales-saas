from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Plan, Subscription, Payment, Coupon, CouponRedemption
# Register your models here.



@admin.register(Plan)
class PlanAdmin(ModelAdmin):
    list_display = ('name', 'tier', 'size', 'billing_frequency', 'price', 'disable_store', 'max_users', 'max_branches', 'max_products', 'created_at')
    search_fields = ('name', 'tier', 'size')
    list_filter = ('tier', 'size', 'billing_frequency')
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
        'duration_in_days',
        'description',
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
    list_display = ('subscription', 'amount', 'payment_method', 'payment_status')
    search_fields = ('subscription__organization__name', 'subscription__plan__name')
    list_filter = ('payment_status',)
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