from django.contrib import admin
from .models import Plan, Subscription, Payment


# Register your models here.



@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'max_users', 'max_branches', 'max_products', 'created_at')
    search_fields = ('name',)
    list_filter = ('name',)
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    list_per_page = 10
    list_display_links = ('name',)    


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
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
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('subscription', 'amount', 'payment_method', 'payment_status')
    search_fields = ('subscription__organization__name', 'subscription__plan__name')
    list_filter = ('payment_status',)
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    list_per_page = 10
    list_display_links = ('subscription', 'amount')
    raw_id_fields = ('subscription',)
    autocomplete_fields = ('subscription',)
