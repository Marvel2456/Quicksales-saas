from django.db import models
from django.contrib.auth.models import AbstractUser
# from tenants.models import Organization

class Branch(models.Model):
    branch_name = models.CharField(max_length=200, blank=True, null=True)
    branch_address = models.CharField(max_length=250, blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "branches"

    def __str__(self):
        return self.branch_name


class Pos(models.Model):
    pos_name = models.CharField(max_length=250, blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'pos'

    def __str__(self):
        return self.pos_name


class CustomUser(AbstractUser):
    organization = models.ForeignKey("tenants.Organization", on_delete=models.CASCADE, blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=True, null=True)
    pos = models.ForeignKey(Pos, on_delete=models.SET_NULL, blank=True, null=True)
    is_admin = models.BooleanField(default = False)
    is_sub_admin = models.BooleanField(default = False)
    is_work_staff = models.BooleanField(default = False)
    phone_number = models.CharField(max_length = 100, blank=True, null=True)
    address = models.CharField(max_length = 200, blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True)


class LoggedIn(models.Model):
    staff = models.ForeignKey(CustomUser, on_delete = models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add = True)
    login_id = models.CharField(max_length = 100)

    def __str__(self):
        return str(self.staff)
# research on adding the loggedin model to each tenants

