from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.mail import send_mail
from django.conf import settings

from .models import (
    CustomUser, Branch, Organization, ActivityLog, OrganizationMembership,
    PromotionalCampaign, PromotionalEmailLog
)
from .tasks import task_send_promotional_campaign
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import Group

from unfold.decorators import action
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
    actions = ['create_promotional_campaign_for_selected']

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

    @admin.action(description="📧 Create Promotional Campaign for Selected Owners")
    def create_promotional_campaign_for_selected(self, request, queryset):
        owners = queryset.filter(role='owner')
        if not owners.exists():
            self.message_user(request, "None of the selected users have the 'owner' role.", level=messages.WARNING)
            return
        campaign = PromotionalCampaign.objects.create(
            subject="Special Announcement for Organization Owners",
            email_body="<p>Dear Owner,</p><p>Enter your promotional message content here...</p>",
            target_audience='selected_owners',
            status='Draft'
        )
        campaign.recipient_owners.set(owners)
        campaign.save()
        self.message_user(request, f"Created Promotional Campaign draft for {owners.count()} owner(s). You can now edit and send it.", level=messages.SUCCESS)
        url = reverse('admin:account_promotionalcampaign_change', args=[campaign.pk])
        return redirect(url)


@admin.register(Branch)
class BranchAdmin(ModelAdmin):
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
class OrganizationAdmin(ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    list_filter = ("created_at",)
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 10
    list_display_links = ("name",)


@admin.register(ActivityLog)
class ActivityLogAdmin(ModelAdmin):
    list_display = ("staff", "activity", "timestamp")
    search_fields = ("staff__email", "activity")
    list_filter = ("activity", "timestamp")
    ordering = ("-timestamp",)
    date_hierarchy = "timestamp"
    list_per_page = 10
    list_display_links = ("staff", "activity")


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(ModelAdmin):
    list_display = ("user", "organization", "branch", "role", "is_active", "date_joined")
    search_fields = ("user__email", "user__first_name", "user__last_name", "organization__name", "branch__name")
    list_filter = ("role", "is_active", "organization", "branch", "date_joined")
    ordering = ("-date_joined",)
    date_hierarchy = "date_joined"
    list_per_page = 20
    list_display_links = ("user", "organization")
    raw_id_fields = ("user", "organization", "branch")
    autocomplete_fields = ("user", "organization", "branch")
    readonly_fields = ("date_joined", "date_removed")
    
    fieldsets = (
        ("Membership Info", {
            "fields": ("user", "organization", "branch", "role", "is_active")
        }),
        ("Dates", {
            "fields": ("date_joined", "date_removed"),
            "classes": ("collapse",)
        }),
    )


class PromotionalEmailLogInline(admin.TabularInline):
    model = PromotionalEmailLog
    extra = 0
    readonly_fields = ('recipient', 'recipient_email', 'status', 'error_message', 'sent_at')
    can_delete = False
    ordering = ('-sent_at',)


@admin.register(PromotionalCampaign)
class PromotionalCampaignAdmin(ModelAdmin):
    list_display = ('subject', 'target_audience', 'status', 'total_recipients', 'sent_count', 'failed_count', 'created_at', 'sent_at')
    list_filter = ('status', 'target_audience', 'created_at')
    search_fields = ('subject', 'email_body')
    filter_horizontal = ('recipient_owners',)
    readonly_fields = ('total_recipients', 'sent_count', 'failed_count', 'created_at', 'sent_at')
    inlines = [PromotionalEmailLogInline]
    actions = ['send_campaign_now', 'send_test_email']
    actions_detail = ['send_campaign_now_detail', 'send_test_email_detail']

    fieldsets = (
        ("Campaign Content", {
            "fields": ("subject", "email_body")
        }),
        ("Targeting", {
            "fields": ("target_audience", "recipient_owners"),
            "description": "Choose target audience segment or select specific organization owners."
        }),
        ("Delivery Status & Metrics", {
            "fields": ("status", "total_recipients", "sent_count", "failed_count", "created_at", "sent_at"),
            "classes": ("collapse",)
        }),
    )

    @action(description="🚀 Send Campaign Now", url_path="send-now")
    def send_campaign_now_detail(self, request, object_id):
        campaign = self.get_object(request, object_id)
        if not campaign:
            self.message_user(request, "Campaign not found.", level=messages.ERROR)
            return redirect(reverse("admin:account_promotionalcampaign_changelist"))
        if campaign.status == 'Sending':
            self.message_user(request, f"Campaign '{campaign.subject}' is already sending.", level=messages.WARNING)
        else:
            task_send_promotional_campaign.delay(str(campaign.id))
            self.message_user(request, f"Dispatched campaign '{campaign.subject}' to Celery background worker for sending.", level=messages.SUCCESS)
        return redirect(reverse("admin:account_promotionalcampaign_change", args=[object_id]))

    @action(description="✉️ Send Test Email to Myself", url_path="send-test")
    def send_test_email_detail(self, request, object_id):
        campaign = self.get_object(request, object_id)
        if not campaign:
            self.message_user(request, "Campaign not found.", level=messages.ERROR)
            return redirect(reverse("admin:account_promotionalcampaign_changelist"))
        admin_email = request.user.email
        if not admin_email:
            self.message_user(request, "Your admin account does not have an email address.", level=messages.ERROR)
        else:
            try:
                html_message = render_to_string(
                    'account/emails/promotional_newsletter.html',
                    {
                        'user': request.user,
                        'subject': f"[TEST] {campaign.subject}",
                        'email_body': campaign.email_body,
                        'recipient_email': admin_email,
                    }
                )
                plain_message = strip_tags(html_message)
                send_mail(
                    subject=f"[TEST] {campaign.subject}",
                    message=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[admin_email],
                    html_message=html_message,
                    fail_silently=False
                )
                self.message_user(request, f"Successfully sent test email to {admin_email}.", level=messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"Failed sending test email: {e}", level=messages.ERROR)
        return redirect(reverse("admin:account_promotionalcampaign_change", args=[object_id]))

    @admin.action(description="🚀 Send Selected Campaigns to Target Owners (Bulk)")
    def send_campaign_now(self, request, queryset):
        sent_tasks = 0
        for campaign in queryset:
            if campaign.status == 'Sending':
                self.message_user(request, f"Campaign '{campaign.subject}' is already sending.", level=messages.WARNING)
                continue
            task_send_promotional_campaign.delay(str(campaign.id))
            sent_tasks += 1
        if sent_tasks > 0:
            self.message_user(request, f"Dispatched {sent_tasks} promotional campaign(s) to Celery background worker.", level=messages.SUCCESS)

    @admin.action(description="✉️ Send Test Email to Myself (Admin)")
    def send_test_email(self, request, queryset):
        admin_email = request.user.email
        if not admin_email:
            self.message_user(request, "Your admin account does not have an email address.", level=messages.ERROR)
            return
        test_count = 0
        for campaign in queryset:
            try:
                html_message = render_to_string(
                    'account/emails/promotional_newsletter.html',
                    {
                        'user': request.user,
                        'subject': f"[TEST] {campaign.subject}",
                        'email_body': campaign.email_body,
                        'recipient_email': admin_email,
                    }
                )
                plain_message = strip_tags(html_message)
                send_mail(
                    subject=f"[TEST] {campaign.subject}",
                    message=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[admin_email],
                    html_message=html_message,
                    fail_silently=False
                )
                test_count += 1
            except Exception as e:
                self.message_user(request, f"Failed sending test email for '{campaign.subject}': {e}", level=messages.ERROR)
        if test_count > 0:
            self.message_user(request, f"Successfully sent {test_count} test email(s) to {admin_email}.", level=messages.SUCCESS)


