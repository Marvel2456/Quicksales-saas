from django.contrib import admin
from .models import CustomUser, Branch, Organization, ActivityLog
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import Group

from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from unfold.admin import ModelAdmin

admin.site.unregister(Group)

@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    model = CustomUser
    list_display = ("email", "first_name", "last_name", "role", "organization", "branch", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active", "organization", "branch")
    search_fields = ("email", "first_name", "last_name", "phone_number")
    ordering = ("email",)

    fieldsets = (
        (("Authentication"), {"fields": ("email", "password")}),
        (("Personal info"), {"fields": ("first_name", "last_name", "phone_number")}),
        (("Organization Info"), {"fields": ("organization", "branch", "role")}),
        (("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "first_name", "last_name", "phone_number", "organization", "branch", "role"),
            },
        ),
    )

    filter_horizontal = ("groups", "user_permissions",)
    list_per_page = 10
    list_display_links = ("email", "first_name", "last_name")


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "created_at")
    search_fields = ("name", "address")
    list_filter = ("created_at",)
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 10
    list_display_links = ("name",)
    raw_id_fields = ("organization",)
    autocomplete_fields = ("organization",)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    list_filter = ("created_at",)
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 10
    list_display_links = ("name",)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("staff", "activity", "timestamp")
    search_fields = ("staff__email", "activity")
    list_filter = ("activity", "timestamp")
    ordering = ("-timestamp",)
    date_hierarchy = "timestamp"
    list_per_page = 10
    list_display_links = ("staff", "activity")
    
