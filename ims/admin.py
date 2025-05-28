from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import Product, Sale, SalesItem, Category, Inventory, Supplier, ErrorTicket

# Register your models here.

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('product_name', 'category')
    search_fields = ('product_name',)
    list_filter = ('category',)
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    list_per_page = 10
    list_display_links = ('product_name',)
    raw_id_fields = ('category',)
    autocomplete_fields = ('category',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('category_name', 'last_updated', 'date_created')
    search_fields = ('category_name',)
    ordering = ('-date_created',)
    date_hierarchy = 'date_created'
    list_per_page = 10
    list_display_links = ('category_name',)