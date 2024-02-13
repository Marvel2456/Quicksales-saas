from django.db import models
from django_tenants.models import TenantMixin, DomainMixin
from account.models import CustomUser
from datetime import timedelta
from django.utils import timezone

# Create your models here.

class Plan(models.Model):
    name = models.CharField(max_length=250, blank=True, null=True)
    price = models.PositiveIntegerField(blank=True, null=True)
    duration_days = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return self.plan_name

class Organization(TenantMixin):
    name = models.CharField(max_length=250, blank=True, null=True)
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='organization_admin', null=True, blank=True)
    subscription_plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True)
    paid_until = models.IntegerField(blank=True, null=True)
    is_subscribed = models.BooleanField(default=False, blank=True)
    is_active = models.BooleanField(default=False, blank=True)

    auto_create_schema = True

    auto_drop_schema = True

    def __str__(self):
        return self.name
    

class Domain(DomainMixin):
    pass
    

class Subscription(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField()

    def save(self, *args, **kwargs):
        self.end_date = self.start_date + timedelta(days=self.plan.duration_days)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.organization.name} - {self.plan.name} Subscription"
    


