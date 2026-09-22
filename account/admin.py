from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.mail import send_mail
from django.conf import settings

from .models import (
    CustomUser, Branch, Organization, ActivityLog, OrganizationMembership,
    PromotionalCampaign, PromotionalEmailLog, SystemAnalytics
)
from subscriptions.models import Subscription, Payment
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth, TruncDate
import json
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


@admin.register(SystemAnalytics)
class SystemAnalyticsAdmin(ModelAdmin):
    change_list_template = "admin/analytics_dashboard.html"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        
        now = timezone.now()
        year_param = request.GET.get('year')
        month_param = request.GET.get('month')

        try:
            from datetime import datetime
            selected_year = int(year_param) if year_param else now.year
            selected_month = int(month_param) if month_param else now.month
            selected_date = timezone.make_aware(datetime(selected_year, selected_month, 1))
        except ValueError:
            selected_year = now.year
            selected_month = now.month
            selected_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        if selected_year == now.year and selected_month == now.month:
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=today_start.weekday())
        else:
            today_start = selected_date
            week_start = selected_date

        month_start = selected_date
        year_start = selected_date.replace(month=1, day=1)
        
        extra_context['selected_year'] = selected_year
        extra_context['selected_month'] = selected_month
        extra_context['available_years'] = range(now.year - 5, now.year + 1)
        # Months dictionary for template
        extra_context['available_months'] = [
            (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
            (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
            (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')
        ]

        # User metrics
        extra_context['users_daily'] = CustomUser.objects.filter(created_at__gte=today_start, created_at__lt=today_start + timedelta(days=1) if today_start.month == now.month else today_start.replace(month=today_start.month%12+1, day=1)).count()
        extra_context['users_weekly'] = CustomUser.objects.filter(created_at__gte=week_start).count()
        extra_context['users_monthly'] = CustomUser.objects.filter(created_at__gte=month_start, created_at__lt=(month_start.replace(month=month_start.month%12+1, day=1) if month_start.month < 12 else month_start.replace(year=month_start.year+1, month=1, day=1))).count()
        extra_context['users_yearly'] = CustomUser.objects.filter(created_at__gte=year_start, created_at__lt=year_start.replace(year=year_start.year+1)).count()
        extra_context['users_total'] = CustomUser.objects.count()

        # Business metrics
        total_businesses = Organization.objects.count()
        active_businesses = Organization.objects.filter(subscriptions__is_active=True).distinct().count()
        extra_context['total_businesses'] = total_businesses
        extra_context['active_subscriptions'] = active_businesses
        extra_context['inactive_subscriptions'] = total_businesses - active_businesses

        # Business Type Chart
        business_types = Organization.objects.values('business_type').annotate(count=Count('id')).order_by('-count')
        biz_labels = [entry['business_type'] or 'Others' for entry in business_types]
        biz_data = [entry['count'] for entry in business_types]
        extra_context['biz_labels'] = json.dumps(biz_labels)
        extra_context['biz_data'] = json.dumps(biz_data)

        # Revenue metrics
        completed_payments = Payment.objects.filter(payment_status='completed')
        
        revenue_monthly = completed_payments.filter(created_at__gte=month_start, created_at__lt=(month_start.replace(month=month_start.month%12+1, day=1) if month_start.month < 12 else month_start.replace(year=month_start.year+1, month=1, day=1))).aggregate(total=Sum('amount'))['total'] or 0
        revenue_annually = completed_payments.filter(created_at__gte=year_start, created_at__lt=year_start.replace(year=year_start.year+1)).aggregate(total=Sum('amount'))['total'] or 0
        extra_context['revenue_monthly'] = float(revenue_monthly)
        extra_context['revenue_annually'] = float(revenue_annually)

        # Revenue Chart Data (last 12 months)
        last_12_months = month_start - timedelta(days=365)
        revenue_by_month = completed_payments.filter(created_at__gte=last_12_months, created_at__lt=month_start.replace(month=month_start.month%12+1, day=1) if month_start.month < 12 else month_start.replace(year=month_start.year+1, month=1, day=1)) \
            .annotate(month=TruncMonth('created_at')) \
            .values('month') \
            .annotate(total_revenue=Sum('amount')) \
            .order_by('month')

        revenue_labels = [entry['month'].strftime("%b %Y") for entry in revenue_by_month if entry['month']]
        revenue_data = [float(entry['total_revenue']) for entry in revenue_by_month if entry['month']]
        
        extra_context['revenue_labels'] = json.dumps(revenue_labels)
        extra_context['revenue_data'] = json.dumps(revenue_data)

        # User Growth Chart Data (last 30 days up to selected month)
        last_30_days = month_start - timedelta(days=30) if month_start.month != now.month else today_start - timedelta(days=30)
        users_by_day = CustomUser.objects.filter(created_at__gte=last_30_days, created_at__lt=month_start.replace(month=month_start.month%12+1, day=1) if month_start.month < 12 else month_start.replace(year=month_start.year+1, month=1, day=1)) \
            .annotate(date=TruncDate('created_at')) \
            .values('date') \
            .annotate(count=Count('id')) \
            .order_by('date')
            
        user_labels = [entry['date'].strftime("%Y-%m-%d") for entry in users_by_day if entry['date']]
        user_data = [entry['count'] for entry in users_by_day if entry['date']]
        
        extra_context['user_labels'] = json.dumps(user_labels)
        extra_context['user_data'] = json.dumps(user_data)

        from django.template.response import TemplateResponse
        context = {
            **self.admin_site.each_context(request),
            'title': 'System Analytics',
            'opts': self.model._meta,
            'has_add_permission': self.has_add_permission(request),
            **extra_context
        }
        return TemplateResponse(request, self.change_list_template, context)


