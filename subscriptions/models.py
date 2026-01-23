from django.db import models
from account.models import Organization
import uuid
from django.db.models import Q, UniqueConstraint
from django.utils import timezone
from decimal import Decimal


class Plan(models.Model):
    TIER_CHOICES = (
        ('basic', 'Basic'),
        ('growth', 'Growth'),
        ('premium', 'Premium'),
    )
    SIZE_CHOICES = (
        ('starter', 'Starter'),
        ('large', 'Large'),
        ('xl', 'XL'),
    )
    BILLING_FREQUENCY_CHOICES = (
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annually', 'Annually'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=255, blank=True, null=True)
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='basic')
    size = models.CharField(max_length=20, choices=SIZE_CHOICES, default='starter')
    billing_frequency = models.CharField(max_length=20, choices=BILLING_FREQUENCY_CHOICES, default='monthly')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_in_days = models.PositiveIntegerField(default=30)
    description = models.TextField(blank=True, null=True)
    max_users = models.IntegerField(default=1)
    max_branches = models.IntegerField(default=1, blank=True, null=True)
    max_products = models.IntegerField(default=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['tier', 'size', 'billing_frequency']
        unique_together = ('tier', 'size', 'billing_frequency')
    

class Coupon(models.Model):
    TYPE_CHOICES = (
        ('percent', 'Percent Off'),
        ('fixed', 'Fixed Amount'),
        ('free_month', 'Free Month'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    code = models.CharField(max_length=50, unique=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    duration_days = models.PositiveIntegerField(default=30)  # used for free_month
    max_uses = models.PositiveIntegerField(default=100)
    uses = models.PositiveIntegerField(default=0)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    def __str__(self):
        return self.code

    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        if self.uses >= self.max_uses:
            return False
        return True


class CouponRedemption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='redemptions')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='coupon_redemptions')
    subscription = models.ForeignKey('Subscription', on_delete=models.CASCADE, related_name='coupon_redemptions', null=True, blank=True)
    used_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.organization} - {self.coupon.code}"


class Subscription(models.Model):
    PROVIDER_CHOICES = (
        ("stripe", "Stripe"),
        ("paystack", "Paystack"),
    )
    CURRENCY_CHOICES = (
        ("USD", "USD"),
        ("NGN", "NGN"),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='subscriptions', blank=True, null=True)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, blank=True, null=True)
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, blank=True, null=True)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, blank=True, null=True)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    def __str__(self):
        return f"{self.organization} - {self.plan}"
    
    class Meta:
        constraints = [
            UniqueConstraint(
                fields=['organization'],
                condition=Q(is_active=True),
                name="unique_active_subscription_per_org"
            )
        ]
    
    def save(self, *args, **kwargs):
        if self.is_active:
            # Deactivate all other subscriptions for this organization
            Subscription.objects.filter(
                organization=self.organization,
                is_active=True
            ).exclude(id=self.id).update(is_active=False)
        super().save(*args, **kwargs)
    

class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=100)
    transaction_id = models.CharField(max_length=255, unique=True)
    STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('completed', 'Completed'),
    ('failed', 'Failed'),
    ]
    payment_status = models.CharField(max_length=100, choices=STATUS_CHOICES, default='pending', blank=True, null=True)
    coupon = models.ForeignKey('Coupon', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.subscription.organization.name} - {self.amount}"