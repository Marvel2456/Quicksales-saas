from django.db import models
from account.models import Organization
import uuid
from django.utils import timezone


class Plan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=255)
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
        unique_together = ('organization', 'is_active')
    
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.subscription.organization.name} - {self.amount}"