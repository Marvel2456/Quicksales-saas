from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import (
    Buyer, StoreListing, ProductListing,
    StoreDiscount, StoreDiscountRedemption,
    OnlineOrder, OnlineOrderItem
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
