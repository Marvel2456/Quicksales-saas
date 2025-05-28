from datetime import date
from django.db import models
from account.models import CustomUser, Branch
from simple_history.models import HistoricalRecords


# Create your models here.
class Category(models.Model):
    category_name = models.CharField(max_length=200, unique=True)
    last_updated = models.DateField(auto_now=True,)
    date_created = models.DateTimeField(auto_now_add=True,)

    class Meta:
        verbose_name_plural = "categories"
    
    def __str__(self):
        return self.category_name

class Product(models.Model):
    product_name = models.CharField(max_length=150, blank=True, null=True, unique=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    brand = models.CharField(max_length=150, blank=True, null=True)
    product_code = models.CharField(max_length=100)
    batch_no = models.CharField(max_length=20, blank=True, null=True)
    unit = models.CharField(max_length=50, blank=True, null=True)
    updated_at = models.DateField(auto_now=True,)
    created_at = models.DateTimeField(auto_now_add=True,)
    profit = models.FloatField(blank=True, null=True)
    
    def __str__(self):
        return self.product_name

class Inventory(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='products')
    quantity = models.IntegerField(default=0)
    quantity_available = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=0, blank=True, null=False)
    choices = (
        ('Available', 'Item is currently available'),
        ('Restocking', 'Currently out of stock'),
    )
    status = models.CharField(max_length=20, choices=choices, default="Available", blank=True, null=True)
    cost_price = models.FloatField(blank=True, null=True)
    sale_price = models.FloatField(blank=True, null=True)
    quantity_restocked = models.IntegerField(default=0, blank=True, null=True)
    count = models.IntegerField(default=0, blank=True, null=True)
    store = models.IntegerField(default=0)
    sold = models.IntegerField(default=0, blank=True, null=True)
    variance = models.IntegerField(default=0)
    available = models.IntegerField(default=0, blank=True, null=True)
    last_updated = models.DateField(auto_now=True,)
    date_created = models.DateTimeField(auto_now_add=True,)
    history = HistoricalRecords()
    
    class Meta:
        verbose_name_plural = "inventories"
        

    def __str__(self):
        return self.product.product_name

    @property
    def store_quantity(self):
        salesitem = self.salesitem_set.all()
        store = self.quantity - sum([item.quantity for item in salesitem])
        return store

    @property
    def quantity_sold(self):
        salesitem = self.salesitem_set.all()
        sold = sum([item.quantity for item in salesitem])
        return sold


class Sale(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    staff = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, blank=True, null=True)
    total_profit = models.FloatField(default=0, blank=True, null=True)
    final_total_price = models.FloatField(default=0, blank=True, null=True)
    discount =  models.FloatField(default=0, blank=True, null=True)
    date_added = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    date_updated = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    transaction_id = models.CharField(max_length=100, null=True)
    choices = (
        ('Cash', 'Cash'),
        ('Transfer', 'Transfer'),
        ('POS', 'POS'),
    )
    method = models.CharField(max_length=50, choices=choices,default="Cash", blank=True, null=True)
    completed = models.BooleanField(default=False)
    history = HistoricalRecords()

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
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    inventory = models.ForeignKey(Inventory, on_delete=models.SET_NULL, blank=True, null=True)
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, blank=True, null=True)
    total = models.FloatField(default=0)
    cost_total = models.FloatField(default=0)
    quantity = models.IntegerField(default=0, blank=True, null=True)
    last_updated = models.DateTimeField(auto_now=True, blank=True, null=True)
    history = HistoricalRecords()
    
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
    staff = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, blank=True, null=True, related_name='error_tickets_assigned')
    title = models.CharField(max_length=150, blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    choices = (
        ('Pending', 'Pending'),
        ('Seen', 'Seen'),
    )
    status = models.CharField(max_length=50, choices=choices,default="Pending", blank=True, null=True)
    date_added = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    date_updated = models.DateTimeField(auto_now=True, blank=True, null=True)

    def __str__(self):
        return str(self.title)
