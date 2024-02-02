from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import Product, Sale, SalesItem, Category, Inventory, Supplier, ErrorTicket

# Register your models here.

class InventoryHistoryAdmin(SimpleHistoryAdmin):
    list_display = ["id", "product", "status"]
    history_list_display = ["status"]
    search_fields = ['product', 'user__username']

class SaleHistoryAdmin(SimpleHistoryAdmin):
    list_display = ["id", "staff", "date_added"]
    history_list_display = ["date_added"]
    search_fields = ['staff__username', 'date_added']


admin.site.register(Product)
admin.site.register(Sale, SaleHistoryAdmin)
admin.site.register(SalesItem)
admin.site.register(Category)
admin.site.register(Inventory, InventoryHistoryAdmin)
admin.site.register(Supplier)
admin.site.register(ErrorTicket)
