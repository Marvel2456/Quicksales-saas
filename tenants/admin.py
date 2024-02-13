from django.contrib import admin
from django_tenants.admin import TenantAdminMixin
from .models import Domain, Organization

# Register your models here.

class DomainInline(admin.TabularInline):

    model = Domain
    max_num = 1

@admin.register(Organization)
class OrganizationAdmin(TenantAdminMixin, admin.ModelAdmin):
        list_display = (
        "admin",
        "is_active",
        "created_on",
        )
        inlines = [DomainInline]
