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
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    country = models.CharField(max_length=300, blank=True, null=True)
    owned_by = models.ForeignKey('account.CustomUser', on_delete=models.CASCADE, related_name='owned_organizations', blank=True, null=True)
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
        ('others', 'Others'),
    ]
    business_type = models.CharField(max_length=50, choices=BUSINESS_CHOICES, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    trial_start = models.DateTimeField(blank=True, null=True)
    trial_end = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "organizations"

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
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=200, blank=True, null=True)
    address = models.CharField(max_length=250, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "branches"

    def __str__(self):
        return self.name


class CustomUser(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=True, null=True)
    role_choice = [
        ('owner', 'Owner'),
        ('manager', 'Manager'),
        ('sales', 'Sales')
    ]
    role = models.CharField(max_length=100, choices=role_choice, default='owner')
    username = None
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length = 100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = CustomUserManager()

    def __str__(self):
        return self.email
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"
    

class ActivityLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=True, null=True)
    staff = models.ForeignKey(CustomUser, on_delete = models.CASCADE)
    activity = models.CharField(max_length=1000)
    timestamp = models.DateTimeField(auto_now_add = True)

    def __str__(self):
        return str(self.staff) + " " + str(self.activity)
    class Meta:
        verbose_name_plural = "activity logs"
        ordering = ['-timestamp']


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
        ('info', 'Info'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=500)
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, default='info')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.email} - {self.notification_type}: {self.message}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Notifications"
        




