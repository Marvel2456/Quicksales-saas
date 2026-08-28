from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager
import uuid
from django.utils.text import slugify
from django.urls import reverse


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get('is_superuser') is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)

class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(unique=True, blank=True, db_index=True)
    country = models.CharField(max_length=300, blank=True, null=True)
    owned_by = models.ForeignKey('account.CustomUser', on_delete=models.CASCADE, related_name='owned_organizations', blank=True, null=True, db_index=True)
    BUSINESS_CHOICES = [
        ('clothing', 'Clothing Store'),
        ('electronics', 'Electronics Store'),
        ('grocery', 'Grocery Store'),
        ('pharmacy', 'Pharmacy'),
        ('bookstore', 'Bookstore'),
        ('convenience', 'Convenience Store'),
        ('accessories', 'Accessories Store'),
        ('hardware', 'Hardware Store'),
        ('department', 'Department Store'),
        ('developer', 'Developer Sandbox'),
        ('others', 'Others'),
    ]
    business_type = models.CharField(max_length=50, choices=BUSINESS_CHOICES, blank=True, null=True)
    logo = models.ImageField(upload_to='organization_logos/', blank=True, null=True)
    brand_color = models.CharField(max_length=7, default='#007bff', blank=True, null=True, help_text='Hex color code (e.g., #007bff)')
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    trial_start = models.DateTimeField(blank=True, null=True)
    trial_end = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name_plural = "organizations"
        indexes = [
            models.Index(fields=['owned_by', '-created_at']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name

    def current_subscription(self):
        return self.subscriptions.filter(is_active=True).order_by('-end_date').first()

    def get_absolute_url(self):
        return reverse('org_login', kwargs={'org_slug': self.slug})

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            base_slug = slugify(self.name)
            slug = base_slug
            count = 1
            while Organization.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{count}"
                count += 1
            self.slug = slug
        super().save(*args, **kwargs)
    
class Branch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, db_index=True)
    name = models.CharField(max_length=200, blank=False, null=False, default="Main Branch", db_index=True)
    address = models.CharField(max_length=250, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name_plural = "branches"
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'name'],
                name='unique_branch_name_per_organization'
            ),
        ]
        indexes = [
            models.Index(fields=['organization', '-created_at']),
        ]

    def __str__(self):
        return self.name


class OrganizationMembership(models.Model):
    """Junction table for many-to-many relationship between users and organizations"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='memberships', db_index=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships', db_index=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='staff_memberships', db_index=True)
    role_choice = [
        ('owner', 'Owner'),
        ('manager', 'Manager'),
        ('sales', 'Sales')
    ]
    role = models.CharField(max_length=100, choices=role_choice, default='sales', db_index=True)
    is_active = models.BooleanField(default=True, db_index=True, help_text='Is this membership active?')
    date_joined = models.DateTimeField(auto_now_add=True, db_index=True)
    date_removed = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "organization memberships"
        unique_together = [('user', 'organization')]
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['branch', 'is_active']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.organization.name} ({self.role})"


class CustomUser(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    role_choice = [
        ('owner', 'Owner'),
        ('manager', 'Manager'),
        ('sales', 'Sales')
    ]
    role = models.CharField(max_length=100, choices=role_choice, default='owner', db_index=True)
    username = None
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length = 100, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    must_change_password = models.BooleanField(default=False, help_text='If True, user must change password on next login')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['role']),
        ]

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = CustomUserManager()

    def __str__(self):
        return self.email
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    # Multi-organization helper methods
    def get_organizations(self):
        """Get all organizations this user is a member of"""
        return Organization.objects.filter(
            memberships__user=self,
            memberships__is_active=True
        ).distinct()
    
    def get_active_memberships(self):
        """Get all active memberships for this user"""
        return self.memberships.filter(is_active=True).select_related('organization', 'branch')
    
    def get_membership_for_organization(self, organization):
        """Get the membership for a specific organization"""
        try:
            return self.memberships.get(organization=organization, is_active=True)
        except OrganizationMembership.DoesNotExist:
            return None
    
    def is_member_of(self, organization):
        """Check if user is an active member of the organization"""
        return self.memberships.filter(organization=organization, is_active=True).exists()
    
    def get_role_in_organization(self, organization):
        """Get user's role in a specific organization"""
        membership = self.get_membership_for_organization(organization)
        return membership.role if membership else None
    
    def get_branch_in_organization(self, organization):
        """Get user's branch in a specific organization"""
        membership = self.get_membership_for_organization(organization)
        return membership.branch if membership else None
    

class ActivityLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    staff = models.ForeignKey(CustomUser, on_delete = models.CASCADE, db_index=True)
    activity = models.CharField(max_length=1000)
    timestamp = models.DateTimeField(auto_now_add = True, db_index=True)

    class Meta:
        verbose_name_plural = "activity logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['organization', '-timestamp']),
        ]

    def __str__(self):
        return str(self.staff) + " " + str(self.activity)


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
        ('info', 'Info'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='notifications', db_index=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='notifications', db_index=True, null=True, blank=True)
    message = models.CharField(max_length=500)
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, default='info')
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Notifications"
        indexes = [
            models.Index(fields=['user', 'is_read']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.notification_type}: {self.message}"


class PromotionalCampaign(models.Model):
    TARGET_AUDIENCE_CHOICES = [
        ('all_owners', 'All Organization Owners'),
        ('active_subscribers', 'Active Subscribers (Paid)'),
        ('trial_owners', 'Trial Owners'),
        ('expired_subscribers', 'Expired Subscribers'),
        ('selected_owners', 'Selected Owners (Specified Below)'),
    ]

    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Sending', 'Sending...'),
        ('Sent', 'Sent'),
        ('Failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    subject = models.CharField(max_length=255, help_text="Email subject line")
    email_body = models.TextField(help_text="HTML or Plain Text content of the newsletter / promotional message")
    target_audience = models.CharField(
        max_length=50, 
        choices=TARGET_AUDIENCE_CHOICES, 
        default='all_owners',
        help_text="Target segment of organization owners"
    )
    recipient_owners = models.ManyToManyField(
        CustomUser, 
        blank=True, 
        limit_choices_to={'role': 'owner'},
        related_name='targeted_campaigns',
        help_text="Specific owners if 'Selected Owners' target audience is chosen"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft', db_index=True)
    total_recipients = models.IntegerField(default=0)
    sent_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Promotional Campaign"
        verbose_name_plural = "Promotional Campaigns"

    def __str__(self):
        return f"{self.subject} [{self.get_status_display()}]"


class PromotionalEmailLog(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Sent', 'Sent'),
        ('Failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    campaign = models.ForeignKey(PromotionalCampaign, on_delete=models.CASCADE, related_name='logs')
    recipient = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_promotions')
    recipient_email = models.EmailField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    error_message = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-sent_at']
        verbose_name = "Promotional Email Log"
        verbose_name_plural = "Promotional Email Logs"

    def __str__(self):
        return f"{self.recipient_email} - {self.campaign.subject} ({self.status})"
