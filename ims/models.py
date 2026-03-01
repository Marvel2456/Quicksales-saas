from datetime import date
from django.db import models
from account.models import Organization, Branch, CustomUser
from simple_history.models import HistoricalRecords
import uuid


# Create your models here.
class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    category_name = models.CharField(max_length=200)
    last_updated = models.DateField(auto_now=True,)
    date_created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(fields=["organization", "category_name"], name="unique_category_per_org"),
        ]
        indexes = [
            models.Index(fields=['organization', '-date_created']),
        ]
    
    def __str__(self):
        return self.category_name

class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    product_name = models.CharField(max_length=150, blank=True, null=True, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, db_index=True)
    brand = models.CharField(max_length=150, blank=True, null=True)
    product_code = models.CharField(max_length=100, db_index=True)
    batch_no = models.CharField(max_length=20, blank=True, null=True)
    unit = models.CharField(max_length=50, blank=True, null=True)
    updated_at = models.DateField(auto_now=True,)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    profit = models.FloatField(blank=True, null=True)
    
    def __str__(self):
        return self.product_name

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "product_name"], name="unique_product_per_org"),
        ]
        indexes = [
            models.Index(fields=['organization', 'category']),
            models.Index(fields=['product_code']),
        ]

class Inventory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, db_index=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='products', db_index=True)
    quantity = models.IntegerField(default=0)
    quantity_available = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=0, blank=True, null=False)
    choices = (
        ('Available', 'Item is currently available'),
        ('Restocking', 'Currently out of stock'),
    )
    status = models.CharField(max_length=20, choices=choices, default="Available", blank=True, null=True, db_index=True)
    cost_price = models.FloatField(blank=True, null=True)
    sale_price = models.FloatField(blank=True, null=True)
    quantity_restocked = models.IntegerField(default=0, blank=True, null=True)
    count = models.IntegerField(default=0, blank=True, null=True)
    store = models.IntegerField(default=0)
    sold = models.IntegerField(default=0, blank=True, null=True)
    variance = models.IntegerField(default=0)
    available = models.IntegerField(default=0, blank=True, null=True)
    last_updated = models.DateField(auto_now=True,)
    date_created = models.DateTimeField(auto_now_add=True, db_index=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = "inventories"
        indexes = [
            models.Index(fields=['organization', 'branch']),
            models.Index(fields=['product', 'branch']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return self.product.product_name

    @property
    def store_quantity(self):
        # Only count items from OPEN (incomplete, non-cancelled) sales
        # Completed or cancelled sales should not reduce available quantity
        open_salesitems = self.salesitem_set.filter(
            sale__completed=False,
            sale__cancelled=False
        )
        store = self.quantity - sum([item.quantity for item in open_salesitems])
        return store

    @property
    def quantity_sold(self):
        # Count items from all sales (for reporting)
        salesitem = self.salesitem_set.all()
        sold = sum([item.quantity for item in salesitem])
        return sold


class Sale(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, db_index=True)
    staff = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, blank=True, null=True, db_index=True)
    total_profit = models.FloatField(default=0, blank=True, null=True)
    final_total_price = models.FloatField(default=0, blank=True, null=True)
    discount =  models.FloatField(default=0, blank=True, null=True)
    date_added = models.DateTimeField(auto_now_add=True, blank=True, null=True, db_index=True)
    date_updated = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    transaction_id = models.CharField(max_length=100, null=True, db_index=True)
    choices = (
        ('Cash', 'Cash'),
        ('Transfer', 'Transfer'),
        ('POS', 'POS'),
    )
    method = models.CharField(max_length=50, choices=choices,default="Cash", blank=True, null=True, db_index=True)
    completed = models.BooleanField(default=False, db_index=True)
    cancelled = models.BooleanField(default=False)
    history = HistoricalRecords()

    class Meta:
        indexes = [
            models.Index(fields=['organization', '-date_added']),
            models.Index(fields=['branch', 'completed']),
            models.Index(fields=['staff', '-date_added']),
            models.Index(fields=['method', '-date_added']),
        ]

    def __str__(self):
        return str(self.transaction_id)

    @property
    def get_cart_total(self):
        salesitem = self.salesitem_set.all()
        total = sum([item.get_total for item in salesitem])
        return total

    @property
    def get_cart_items(self):
        salesitem = self.salesitem_set.all()
        total = sum([item.quantity for item in salesitem])
        return total

    @property
    def get_total_profit(self):
        salesitem = self.salesitem_set.all()
        profit = sum([item.get_profit for item in salesitem])
        return profit
        # display daily profits on the dashboard and on the sales page
        #time based welcome greeting with javascript

    @property
    def get_total_cost_price(self):
        salesitem = self.salesitem_set.all()
        cost_price = sum([item.get_cost_total for item in salesitem])
        return cost_price


class SalesItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, db_index=True)
    inventory = models.ForeignKey(Inventory, on_delete=models.SET_NULL, blank=True, null=True, db_index=True)
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, blank=True, null=True, db_index=True)
    total = models.FloatField(default=0)
    cost_total = models.FloatField(default=0)
    quantity = models.IntegerField(default=0, blank=True, null=True)
    last_updated = models.DateTimeField(auto_now=True, blank=True, null=True)
    history = HistoricalRecords()

    class Meta:
        indexes = [
            models.Index(fields=['sale', '-last_updated']),
            models.Index(fields=['organization', 'branch']),
        ]
    
    def __str__(self):
        return str(self.inventory)
    
    @property
    def get_total(self):
        total = self.inventory.sale_price * self.quantity
        return total

    @property
    def get_cost_total(self):
        total = self.inventory.cost_price * self.quantity
        return total

    @property
    def get_profit(self):
        profit = self.get_total - self.get_cost_total
        return profit

class Supplier(models.Model):
    supplier_name = models.CharField(max_length=250, blank=True, null=True)
    supplier_number = models.CharField(max_length=100, blank=True, null=True)
    supplies = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.supplier_name

class ErrorTicket(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    staff = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, blank=True, null=True, related_name='error_tickets_created', db_index=True)
    assigned_to = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, blank=True, null=True, related_name='error_tickets_assigned', db_index=True)
    title = models.CharField(max_length=150, blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    description = models.TextField(blank=True, null=True)
    choices = (
        ('Pending', 'Pending'),
        ('Seen', 'Seen'),
    )
    status = models.CharField(max_length=50, choices=choices,default="Pending", blank=True, null=True, db_index=True)
    date_added = models.DateTimeField(auto_now_add=True, blank=True, null=True, db_index=True)
    date_updated = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['assigned_to', '-date_added']),
        ]

    def __str__(self):
        return str(self.title)


class TicketComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    ticket = models.ForeignKey(ErrorTicket, on_delete=models.CASCADE, related_name='comments', db_index=True)
    author = models.ForeignKey(CustomUser, on_delete=models.CASCADE, db_index=True)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['ticket', '-created_at']),
        ]

    def __str__(self):
        return f"Comment by {self.author.email} on {self.ticket.title}"


class Invoice(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('closed', 'Closed'),
    ]
    PAYMENT_CHOICES = [
        ('Cash', 'Cash'),
        ('Transfer', 'Transfer'),
        ('POS', 'POS'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, blank=True, null=True, db_index=True)
    # Customer info — typed in manually by owner on invoice creation
    customer_name = models.CharField(max_length=255, blank=True, null=True)
    customer_email = models.EmailField(blank=True, null=True)
    customer_phone = models.CharField(max_length=50, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    due_date = models.DateField(blank=True, null=True)
    total_amount = models.FloatField(default=0, blank=True, null=True)
    payment_method = models.CharField(max_length=50, choices=PAYMENT_CHOICES, blank=True, null=True)
    invoice_number = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    date_created = models.DateTimeField(auto_now_add=True, blank=True, null=True, db_index=True)
    date_updated = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization', '-date_created']),
            models.Index(fields=['branch', 'status']),
        ]

    def __str__(self):
        return f"Invoice #{self.invoice_number} - {self.customer_name}"

    @property
    def get_total(self):
        return sum(item.total or 0 for item in self.items.all())


class InvoiceItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items', blank=True, null=True, db_index=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, blank=True, null=True)
    inventory = models.ForeignKey(Inventory, on_delete=models.SET_NULL, blank=True, null=True, db_index=True)
    quantity = models.IntegerField(default=1, blank=True, null=True)
    unit_price = models.FloatField(blank=True, null=True)   # snapshot of sale_price at invoice creation
    total = models.FloatField(default=0, blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['invoice']),
        ]

    def __str__(self):
        return f"{self.inventory} x{self.quantity}"

    def save(self, *args, **kwargs):
        if self.unit_price and self.quantity:
            self.total = self.unit_price * self.quantity
        super().save(*args, **kwargs)
