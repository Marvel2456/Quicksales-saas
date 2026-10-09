import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from account.models import Organization, Branch
from ims.models import Product, Inventory, Sale


class Buyer(models.Model):
    """
    A customer account that is NOT tied to any single organization.
    Can browse and purchase from any vendor storefront.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=50, blank=True)
    password = models.CharField(max_length=128)
    shipping_address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.get_full_name() or self.email

    def get_full_name(self):
        full = f"{self.first_name} {self.last_name}".strip()
        return full if full else self.email

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)


class StoreListing(models.Model):
    """
    Public-facing storefront settings for an organization.
    Stock is powered by the organization's default_branch.
    """
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name='store')
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='store_listings',
        help_text='The branch whose inventory is used for the online store. Defaults to organization default branch.'
    )
    is_active = models.BooleanField(default=True, help_text='Toggle to enable/disable public storefront.')
    tagline = models.CharField(max_length=255, blank=True, help_text='Short slogan or welcome banner')
    announcement = models.TextField(blank=True, help_text='Top announcement banner on the storefront')
    banner = models.ImageField(upload_to='store_banners/', blank=True, null=True)
    contact_email = models.EmailField(blank=True, help_text='Customer support email')
    online_store_email = models.EmailField(blank=True, help_text="Email to receive order notifications alongside the shop owner's email")
    contact_phone = models.CharField(max_length=50, blank=True)
    instagram_handle = models.CharField(max_length=100, blank=True, help_text='e.g. yourstore')
    whatsapp_number = models.CharField(max_length=50, blank=True, help_text='WhatsApp phone with country code')
    primary_color = models.CharField(max_length=7, default='#2563eb', blank=True, null=True, help_text='Primary brand/theme color hex (e.g. #2563eb)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.organization.name} Store"

    @property
    def get_brand_color(self):
        return self.primary_color or getattr(self.organization, 'brand_color', None) or '#2563eb'

    def get_active_branch(self):
        """Returns the active branch powering stock (either configured branch, org default_branch, or first branch)."""
        return self.branch or self.organization.default_branch or self.organization.branch_set.first()

    def save(self, *args, **kwargs):
        if not self.branch_id and self.organization_id:
            self.branch = self.organization.default_branch
        super().save(*args, **kwargs)


class ProductListing(models.Model):
    """
    Links a specific Branch Inventory item to the public storefront.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(StoreListing, on_delete=models.CASCADE, related_name='listings')
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name='store_listings')
    is_visible = models.BooleanField(default=True, help_text='Display on public store')
    featured = models.BooleanField(default=False, help_text='Show in featured products section')
    custom_title = models.CharField(max_length=200, blank=True, help_text='Optional override for product name')
    custom_description = models.TextField(blank=True, help_text='Product description shown to buyers')
    image = models.ImageField(upload_to='store_products/', blank=True, null=True, help_text="Override primary photo")
    image_detail = models.ImageField(upload_to='store_products/', blank=True, null=True, help_text="Override secondary/detail photo")
    image_extra = models.ImageField(upload_to='store_products/', blank=True, null=True, help_text="Override tertiary/extra photo")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('store', 'inventory')
        ordering = ['-featured', '-created_at']

    def __str__(self):
        return f"{self.display_title} ({self.store.organization.name})"

    @property
    def display_title(self):
        return self.custom_title or (self.inventory.product.product_name if self.inventory and self.inventory.product else 'Unnamed Item')

    @property
    def display_price(self):
        return self.inventory.sale_price if self.inventory else 0

    @property
    def stock_quantity(self):
        if not self.inventory:
            return 0
        # Priority: store_quantity property, then quantity, then quantity_available
        qty = getattr(self.inventory, 'store_quantity', None)
        if qty is None:
            qty = self.inventory.quantity if self.inventory.quantity is not None else self.inventory.quantity_available
        return max(0, qty or 0)

    @property
    def is_in_stock(self):
        if not self.inventory:
            return False
        return bool(self.stock_quantity > 0 and self.inventory.status != 'Restocking')

    @property
    def get_image_url(self):
        if self.image:
            try:
                return self.image.url
            except Exception:
                pass
        if self.inventory and self.inventory.product and self.inventory.product.image:
            try:
                return self.inventory.product.image.url
            except Exception:
                pass
        return None

    @property
    def get_image_detail_url(self):
        if self.image_detail:
            try:
                return self.image_detail.url
            except Exception:
                pass
        if self.inventory and self.inventory.product and getattr(self.inventory.product, 'image_detail', None):
            try:
                return self.inventory.product.image_detail.url
            except Exception:
                pass
        return None

    @property
    def get_image_extra_url(self):
        if self.image_extra:
            try:
                return self.image_extra.url
            except Exception:
                pass
        if self.inventory and self.inventory.product and getattr(self.inventory.product, 'image_extra', None):
            try:
                return self.inventory.product.image_extra.url
            except Exception:
                pass
        return None

    @property
    def get_images(self):
        """Returns a list of valid image URLs (up to 3 images: primary + detail + extra)."""
        images = []
        primary = self.get_image_url
        if primary:
            images.append(primary)
        detail = self.get_image_detail_url
        if detail and detail not in images:
            images.append(detail)
        extra = self.get_image_extra_url
        if extra and extra not in images:
            images.append(extra)
        return images


class StoreDiscount(models.Model):
    """
    Vendor-generated discount coupons for their online store.
    """
    TYPE_CHOICES = [
        ('percent', 'Percentage Off (%)'),
        ('fixed', 'Fixed Amount Off'),
    ]
    SCOPE_CHOICES = [
        ('entire_order', 'Entire Order'),
        ('product', 'Specific Products Only'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='store_discounts')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    code = models.CharField(max_length=50, help_text='Coupon code buyers enter at checkout (e.g. SALLAH20)')
    label = models.CharField(max_length=100, blank=True, help_text='Campaign name (e.g. "Black Friday 2026")')
    discount_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='percent')
    value = models.DecimalField(max_digits=10, decimal_places=2, help_text='Percent (e.g. 15 for 15%) or Fixed Amount')
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='entire_order')
    products = models.ManyToManyField(Product, blank=True, help_text='Selected products if scope is Specific Products')
    max_uses = models.PositiveIntegerField(default=0, help_text='0 = unlimited')
    uses = models.PositiveIntegerField(default=0)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(blank=True, null=True, help_text='Leave empty for no expiry')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'code')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.code} — {self.organization.name}"

    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        if self.max_uses > 0 and self.uses >= self.max_uses:
            return False
        return True


class OnlineOrder(models.Model):
    """
    An order placed by a buyer from the online store.
    Designed for seamless manual and automated fulfillment for online/Instagram vendors.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('confirmed', 'Confirmed & Reserved'),
        ('dispatched', 'Dispatched / In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=50, unique=True, db_index=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='online_orders')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    buyer = models.ForeignKey(Buyer, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    
    # Guest or snapshot buyer info
    buyer_name = models.CharField(max_length=255)
    buyer_email = models.EmailField()
    buyer_phone = models.CharField(max_length=50, blank=True)
    shipping_address = models.TextField(blank=True)
    customer_notes = models.TextField(blank=True, help_text='Special delivery instructions')

    # Linked IMS sale record (created on confirmation to synchronize POS & inventory)
    sale = models.OneToOneField(Sale, on_delete=models.SET_NULL, null=True, blank=True, related_name='online_order')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    payment_method = models.CharField(max_length=50, default='squadco', choices=[('squadco', 'SquadCo (Card / Transfer / USSD)'), ('cod', 'Pay on Delivery / Manual Confirmation')])
    payment_status = models.CharField(max_length=20, default='pending', choices=[('pending', 'Pending Payment'), ('paid', 'Paid'), ('failed', 'Payment Failed')], db_index=True)
    payment_reference = models.CharField(max_length=100, blank=True, db_index=True)
    paid_at = models.DateTimeField(blank=True, null=True)

    currency = models.CharField(max_length=10, default='NGN')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount = models.ForeignKey(StoreDiscount, on_delete=models.SET_NULL, null=True, blank=True)

    # Fulfillment tracking
    dispatch_note = models.TextField(blank=True, help_text='Tracking notes, rider info, or courier receipt')
    courier_name = models.CharField(max_length=100, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    dispatched_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancelled_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.order_number} ({self.organization.name})"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"QS-{timezone.now().strftime('%y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)


class OnlineOrderItem(models.Model):
    """
    Individual items inside an online order.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(OnlineOrder, on_delete=models.CASCADE, related_name='items')
    product_listing = models.ForeignKey(ProductListing, on_delete=models.SET_NULL, null=True, blank=True)
    inventory = models.ForeignKey(Inventory, on_delete=models.SET_NULL, null=True, blank=True)
    product_name = models.CharField(max_length=255)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

    def save(self, *args, **kwargs):
        self.total_price = Decimal(str(self.unit_price)) * self.quantity
        super().save(*args, **kwargs)


class StoreDiscountRedemption(models.Model):
    """
    Audit log of coupon code usage per order.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    discount = models.ForeignKey(StoreDiscount, on_delete=models.CASCADE, related_name='redemptions')
    order = models.ForeignKey(OnlineOrder, on_delete=models.CASCADE, related_name='discount_redemptions')
    buyer = models.ForeignKey(Buyer, on_delete=models.SET_NULL, null=True, blank=True)
    amount_saved = models.DecimalField(max_digits=12, decimal_places=2)
    redeemed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.discount.code} redeemed on Order #{self.order.order_number}"


class StoreBankAccount(models.Model):
    """
    Vendor settlement bank account for receiving online store payouts / withdrawals.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name='store_bank_account')
    bank_name = models.CharField(max_length=100)
    bank_code = models.CharField(max_length=20, blank=True)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.bank_name} - {self.account_number} ({self.organization.name})"


class StorePayout(models.Model):
    """
    Withdrawal / Payout requests made by the store owner for online store sales revenue.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('processing', 'Processing Transfer'),
        ('completed', 'Completed / Paid'),
        ('rejected', 'Rejected / Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=50, unique=True, db_index=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='payouts')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='NGN')
    
    # Snapshot of bank details at time of request
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=200)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    notes = models.TextField(blank=True, help_text='Owner withdrawal notes')
    admin_notes = models.TextField(blank=True, help_text='Transfer receipt or remarks')
    
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payout #{self.reference} — {self.organization.name} (₦{self.amount})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"WD-{timezone.now().strftime('%y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

