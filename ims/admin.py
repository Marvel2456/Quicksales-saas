from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from unfold.decorators import display
from .models import Product, Sale, SalesItem, Category, Inventory, Supplier, ErrorTicket

# Register your models here.

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('organization', 'branch', 'product_name', 'category')
    search_fields = ('organization', 'branch', 'product_name')
    list_filter = ('category',)
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    list_per_page = 10
    list_display_links = ('product_name',)
    raw_id_fields = ('category',)
    autocomplete_fields = ('category',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('organization', 'branch', 'category_name', 'last_updated', 'date_created')
    search_fields = ('organization', 'branch','category_name',)
    ordering = ('-date_created',)
    date_hierarchy = 'date_created'
    list_per_page = 10
    list_display_links = ('category_name',)


class SalesItemInline(admin.TabularInline):
    model = SalesItem
    extra = 0
    readonly_fields = ['get_total', 'get_cost_total', 'get_profit']
    fields = ['inventory', 'quantity', 'get_total', 'get_cost_total', 'get_profit']
    autocomplete_fields = ['inventory']
    show_change_link = True

    @display(description="Total")
    def get_total(self, obj):
        return obj.get_total

    @display(description="Cost Total")
    def get_cost_total(self, obj):
        return obj.get_cost_total

    @display(description="Profit")
    def get_profit(self, obj):
        return obj.get_profit


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ['organization', 'branch', 'product', 'quantity', 'quantity_available', 'status', 'store_quantity', 'quantity_sold', 'last_updated']
    search_fields = ['organization', 'product__product_name', 'branch__name']
    list_filter = ['status', 'branch', 'product']
    readonly_fields = ['store_quantity', 'quantity_sold', 'last_updated', 'date_created']
    autocomplete_fields = ['organization', 'branch', 'product']
    fieldsets = (
        ("Product Info", {
            "fields": ("organization", "branch", "product", "status")
        }),
        ("Stock Details", {
            "fields": ("quantity", "quantity_available", "reorder_level", "quantity_restocked", "store", "sold", "variance", "available")
        }),
        ("Pricing", {
            "fields": ("cost_price", "sale_price")
        }),
        ("Computed Fields", {
            "fields": ("store_quantity", "quantity_sold", "last_updated", "date_created")
        }),
    )


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['transaction_id', 'branch', 'staff', 'get_cart_total', 'get_cart_items', 'get_total_profit', 'completed', 'date_added']
    search_fields = ['transaction_id', 'branch__name', 'staff__username']
    list_filter = ['completed', 'method', 'branch']
    readonly_fields = ['get_cart_total', 'get_cart_items', 'get_total_profit', 'get_total_cost_price', 'date_added', 'date_updated']
    inlines = [SalesItemInline]
    autocomplete_fields = ['organization', 'branch', 'staff']

    fieldsets = (
        ("Transaction Info", {
            "fields": ("transaction_id", "organization", "branch", "staff", "method", "completed")
        }),
        ("Financial Summary", {
            "fields": ("final_total_price", "discount", "get_total_cost_price", "get_cart_total", "get_cart_items", "get_total_profit")
        }),
        ("Timestamps", {
            "fields": ("date_added", "date_updated")
        }),
    )


@admin.register(SalesItem)
class SalesItemAdmin(admin.ModelAdmin):
    list_display = ['inventory', 'sale', 'quantity', 'get_total', 'get_cost_total', 'get_profit', 'last_updated']
    search_fields = ['inventory__product__product_name', 'sale__transaction_id']
    autocomplete_fields = ['organization', 'branch', 'inventory', 'sale']
    readonly_fields = ['get_total', 'get_cost_total', 'get_profit', 'last_updated']

    fieldsets = (
        ("Sales Item Info", {
            "fields": ("organization", "branch", "inventory", "sale", "quantity")
        }),
        ("Computed Totals", {
            "fields": ("get_total", "get_cost_total", "get_profit", "last_updated")
        }),
    )