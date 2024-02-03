from django.db import models
from django_tenants.models import TenantMixin, DomainMixin
from account.models import CustomUser

# Create your models here.

class Plan(models.Model):
    plan_name = models.CharField(max_length=250, blank=True, null=True)
    price = models.PositiveIntegerField(blank=True, null=True)
    duration_days = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return self.plan_name

class Organization(TenantMixin):
    business_name = models.CharField(max_length=250, blank=True, null=True)
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE, null=True, blank=True)
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True)
    paid_until = models.IntegerField(blank=True, null=True)
    is_active = models.BooleanField(default=False, blank=True)

    auto_create_schema = True

    auto_drop_schema = True

    def __str__(self):
        return self.business_name
    


