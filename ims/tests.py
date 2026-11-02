from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from ims.models import Category, Product, Inventory, Sale, SalesItem, ErrorTicket, OfflineSaleTemp
from account.models import Organization, Branch
from subscriptions.models import Plan, Subscription
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import json
import uuid

User = get_user_model()

class OfflineAPITests(TestCase):
    def setUp(self):
        # Create test organization and branch
        self.organization = Organization.objects.create(name="Test Organization")
        self.branch = Branch.objects.create(name="Test Branch", organization=self.organization)
        
        # Create subscription to bypass middleware redirect
        self.plan, _ = Plan.objects.get_or_create(
            tier='basic',
            size='starter',
            billing_frequency='monthly',
            defaults={'price': Decimal('99.00')}
        )
        self.subscription = Subscription.objects.create(
            organization=self.organization,
            plan=self.plan,
            is_active=True,
            end_date=timezone.now() + timedelta(days=30)
        )
        
        # Create user with owner privileges
        self.user = User.objects.create_user(
            email="posowner@example.com",
            password="testpassword123",
            first_name="Store",
            last_name="Owner",
            is_active=True
        )
        # Setup organization relationship (membership)
        from account.models import OrganizationMembership
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.organization,
            branch=self.branch,
            role="owner"
        )
        self.user.branch = self.branch
        self.user.save()
        
        # Log in the client
        self.client = Client()
        self.client.login(email="posowner@example.com", password="testpassword123")
        
        # Setup catalog items
        self.category = Category.objects.create(
            category_name="Electronics",
            branch=self.branch,
            organization=self.organization
        )
        
        self.product = Product.objects.create(
            product_name="Wireless Mouse",
            category=self.category,
            product_code="MOUSE001",
            branch=self.branch,
            organization=self.organization
        )
        
        self.inventory = Inventory.objects.create(
            product=self.product,
            branch=self.branch,
            organization=self.organization,
            quantity=15,
            cost_price=10.0,
            sale_price=25.0
        )

    def test_get_offline_data_success(self):
        url = reverse('get_offline_data', kwargs={'pk': self.branch.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertIn('products', data)
        self.assertIn('categories', data)
        self.assertEqual(len(data['products']), 1)
        self.assertEqual(data['products'][0]['product_name'], "Wireless Mouse")
        self.assertEqual(data['products'][0]['store_quantity'], 15)
        self.assertEqual(data['products'][0]['sale_price'], 25.0)

    def test_sync_sale_success(self):
        temp_id = "temp_sale_uuid_123"
        url = reverse('sync_sale', kwargs={'pk': self.branch.id})
        payload = {
            'tempId': temp_id,
            'method': 'Cash',
            'items': [
                {'inventory_id': str(self.inventory.id), 'quantity': 2}
            ]
        }
        
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 201)
        
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('sale_id', data)
        
        # Verify database entities
        sale = Sale.objects.get(id=data['sale_id'])
        self.assertEqual(sale.transaction_id, temp_id)
        self.assertEqual(sale.final_total_price, 50.0) # 25.0 * 2
        self.assertEqual(sale.total_profit, 30.0)      # (25.0 - 10.0) * 2
        self.assertEqual(sale.method, 'Cash')
        self.assertTrue(sale.completed)
        
        # Verify inventory decrement
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 13) # 15 - 2
        
        # Verify idempotency record
        self.assertTrue(OfflineSaleTemp.objects.filter(temp_id=temp_id).exists())

    def test_sync_sale_idempotency(self):
        temp_id = "temp_sale_uuid_dup"
        url = reverse('sync_sale', kwargs={'pk': self.branch.id})
        payload = {
            'tempId': temp_id,
            'method': 'Transfer',
            'items': [
                {'inventory_id': str(self.inventory.id), 'quantity': 3}
            ]
        }
        
        # First sync
        response1 = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response1.status_code, 201)
        data1 = json.loads(response1.content)
        sale_id = data1['sale_id']
        
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 12) # 15 - 3
        
        # Second identical sync (simulating network retry/duplicate)
        response2 = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response2.status_code, 200) # Should be 200 OK
        data2 = json.loads(response2.content)
        self.assertEqual(data2['sale_id'], sale_id)
        self.assertIn('Already synced', data2['message'])
        
        # Verify no double decrement in inventory
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 12) # Still 12, not 9

    def test_sync_sale_stock_conflict(self):
        temp_id = "temp_sale_uuid_shortage"
        url = reverse('sync_sale', kwargs={'pk': self.branch.id})
        payload = {
            'tempId': temp_id,
            'method': 'POS',
            'items': [
                {'inventory_id': str(self.inventory.id), 'quantity': 20} # Exceeds 15 in stock
            ]
        }
        
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 409) # Should return 409 Conflict
        data = json.loads(response.content)
        self.assertIn('Insufficient stock', data['error'])
        
        # Verify no sale created in database
        self.assertFalse(Sale.objects.filter(transaction_id=temp_id).exists())
        
        # Verify inventory unchanged
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 15)
        
        # Verify ErrorTicket created
        self.assertTrue(ErrorTicket.objects.filter(
            title__icontains="Offline Sync Shortage",
            branch=self.branch
        ).exists())

    # --- Unified online/offline cart ---------------------------------------

    def _open_sale(self, qty=2, staff=None):
        sale = Sale.objects.create(staff=staff or self.user, branch=self.branch, organization=self.organization)
        SalesItem.objects.create(
            sale=sale, branch=self.branch, organization=self.organization,
            inventory=self.inventory, quantity=qty
        )
        return sale

    def _post_json(self, name, payload):
        url = reverse(name, kwargs={'pk': self.branch.id})
        return self.client.post(url, data=json.dumps(payload), content_type='application/json')

    def test_sync_sale_completes_existing_online_sale(self):
        sale = self._open_sale(qty=2)
        # Cashier added one more unit while offline, then checked out
        response = self._post_json('sync_sale', {
            'tempId': 'offline_continue_1',
            'server_sale_id': str(sale.id),
            'method': 'POS',
            'items': [{'inventory_id': str(self.inventory.id), 'quantity': 3}],
        })
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.content)
        self.assertEqual(data['sale_id'], str(sale.id))
        self.assertTrue(data['continued_online_sale'])

        # No second Sale was created
        self.assertEqual(Sale.objects.filter(branch=self.branch).count(), 1)
        sale.refresh_from_db()
        self.assertTrue(sale.completed)
        self.assertEqual(sale.method, 'POS')
        self.assertEqual(sale.final_total_price, 75.0)
        self.assertEqual(sale.salesitem_set.count(), 1)
        self.assertEqual(sale.salesitem_set.first().quantity, 3)

        # Stock decremented exactly once and no reservation left behind
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 12)
        self.assertEqual(self.inventory.store_quantity, 12)

    def test_sync_sale_rejects_when_online_sale_already_completed(self):
        sale = self._open_sale(qty=2)
        sale.completed = True
        sale.save()

        response = self._post_json('sync_sale', {
            'tempId': 'offline_conflict_1',
            'server_sale_id': str(sale.id),
            'method': 'Cash',
            'items': [{'inventory_id': str(self.inventory.id), 'quantity': 2}],
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Sale.objects.filter(branch=self.branch).count(), 1)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 15)
        self.assertTrue(ErrorTicket.objects.filter(
            title__icontains="Offline Sync Conflict", branch=self.branch
        ).exists())

    def test_get_open_sales_returns_only_own_open_sales(self):
        own = self._open_sale(qty=2)
        closed = self._open_sale(qty=1)
        closed.completed = True
        closed.save()
        other_user = User.objects.create_user(email="other@example.com", password="x12345678", is_active=True)
        self._open_sale(qty=1, staff=other_user)

        response = self.client.get(reverse('get_open_sales', kwargs={'pk': self.branch.id}))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual([s['id'] for s in data['sales']], [str(own.id)])
        self.assertEqual(data['sales'][0]['items'][0]['quantity'], 2)
        self.assertEqual(data['active_sale_id'], str(own.id))

    def test_sync_cart_updates_existing_open_sale(self):
        sale = self._open_sale(qty=2)
        response = self._post_json('sync_cart', {
            'local_id': str(sale.id),
            'server_sale_id': str(sale.id),
            'items': [{'inventory_id': str(self.inventory.id), 'quantity': 5}],
            'make_active': True,
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['server_sale_id'], str(sale.id))
        self.assertEqual(data['adjustments'], [])
        self.assertEqual(sale.salesitem_set.get().quantity, 5)
        self.assertEqual(self.client.session.get(f'active_sale_{self.branch.id}'), str(sale.id))

    def test_sync_cart_caps_to_available_stock(self):
        sale = self._open_sale(qty=3)
        # Another cashier reserved 10 of the 15 units meanwhile
        other_user = User.objects.create_user(email="cashier2@example.com", password="x12345678", is_active=True)
        self._open_sale(qty=10, staff=other_user)

        response = self._post_json('sync_cart', {
            'local_id': str(sale.id),
            'server_sale_id': str(sale.id),
            'items': [{'inventory_id': str(self.inventory.id), 'quantity': 8}],
        })
        data = json.loads(response.content)
        # 15 total - 10 held by the other cart = 5 available to this cart
        self.assertEqual(sale.salesitem_set.get().quantity, 5)
        self.assertEqual(len(data['adjustments']), 1)
        self.assertEqual(data['adjustments'][0]['requested'], 8)
        self.assertEqual(data['adjustments'][0]['applied'], 5)

    def test_sync_cart_creates_sale_for_offline_cart_idempotently(self):
        payload = {
            'local_id': 'temp-sale-abc123',
            'items': [{'inventory_id': str(self.inventory.id), 'quantity': 2}],
        }
        first = json.loads(self._post_json('sync_cart', payload).content)
        second = json.loads(self._post_json('sync_cart', payload).content)
        self.assertEqual(first['server_sale_id'], second['server_sale_id'])
        self.assertEqual(Sale.objects.filter(branch=self.branch, completed=False).count(), 1)

    def test_sync_cart_applies_offline_cancel(self):
        sale = self._open_sale(qty=2)
        response = self._post_json('sync_cart', {
            'local_id': str(sale.id),
            'server_sale_id': str(sale.id),
            'items': [],
            'cancelled': True,
        })
        self.assertEqual(response.status_code, 200)
        sale.refresh_from_db()
        self.assertTrue(sale.cancelled)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.store_quantity, 15)

    def test_sync_cart_moves_items_when_sale_closed_elsewhere(self):
        sale = self._open_sale(qty=2)
        sale.completed = True
        sale.save()
        data = json.loads(self._post_json('sync_cart', {
            'local_id': str(sale.id),
            'server_sale_id': str(sale.id),
            'items': [{'inventory_id': str(self.inventory.id), 'quantity': 1}],
        }).content)
        self.assertTrue(data['conflict'])
        self.assertNotEqual(data['server_sale_id'], str(sale.id))
        new_sale = Sale.objects.get(id=data['server_sale_id'])
        self.assertFalse(new_sale.completed)
        self.assertEqual(new_sale.salesitem_set.get().quantity, 1)

    def test_sync_sale_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(email="posowner@example.com", password="testpassword123")
        response = csrf_client.post(
            reverse('sync_sale', kwargs={'pk': self.branch.id}),
            data=json.dumps({'tempId': 'offline_csrf', 'items': [{'inventory_id': str(self.inventory.id), 'quantity': 1}]}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Sale.objects.filter(transaction_id='offline_csrf').exists())


class ProductImageWebPOptimizerTests(TestCase):
    def setUp(self):
        from PIL import Image
        self.org = Organization.objects.create(name="Image Test Org", slug="image-test-org", is_active=True)
        self.branch = Branch.objects.create(name="Main Branch", organization=self.org)
        self.category = Category.objects.create(organization=self.org, branch=self.branch, category_name="Shoes")
        plan, _ = Plan.objects.get_or_create(
            tier='basic',
            size='starter',
            billing_frequency='monthly',
            defaults={'price': Decimal('99.00')}
        )
        Subscription.objects.create(
            organization=self.org,
            plan=plan,
            is_active=True,
            end_date=timezone.now() + timedelta(days=30)
        )

    def test_optimize_product_image_jpeg(self):
        """Test large JPEG image is downscaled to max 1600px and converted to WebP"""
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from ims.utils.image_optimizer import optimize_product_image

        # Create a 2400x1800 raw test image in memory
        img = Image.new('RGB', (2400, 1800), color=(200, 50, 50))
        img_io = io.BytesIO()
        img.save(img_io, format='JPEG', quality=95)
        img_io.seek(0)

        uploaded = SimpleUploadedFile("summer_shoes.jpg", img_io.read(), content_type="image/jpeg")
        optimized_file = optimize_product_image(uploaded)

        self.assertIsNotNone(optimized_file)
        self.assertTrue(optimized_file.name.endswith('.webp'))

        # Open optimized image and verify format & dimension constraints
        result_img = Image.open(optimized_file)
        self.assertEqual(result_img.format, 'WEBP')
        self.assertLessEqual(result_img.width, 1600)
        self.assertLessEqual(result_img.height, 1600)
        # Verify aspect ratio preserved: 2400x1800 -> 1600x1200
        self.assertEqual(result_img.size, (1600, 1200))

    def test_optimize_product_image_png_transparency(self):
        """Test PNG with transparency converts to WebP preserving RGBA mode"""
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from ims.utils.image_optimizer import optimize_product_image

        img = Image.new('RGBA', (500, 500), color=(0, 100, 200, 128))
        img_io = io.BytesIO()
        img.save(img_io, format='PNG')
        img_io.seek(0)

        uploaded = SimpleUploadedFile("logo.png", img_io.read(), content_type="image/png")
        optimized_file = optimize_product_image(uploaded)

        self.assertIsNotNone(optimized_file)
        self.assertTrue(optimized_file.name.endswith('.webp'))

        result_img = Image.open(optimized_file)
        self.assertEqual(result_img.format, 'WEBP')
        self.assertEqual(result_img.mode, 'RGBA')

    def test_product_form_with_image_upload(self):
        """Test ProductForm cleans and optimizes uploaded image to WebP"""
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from ims.forms import ProductForm

        img = Image.new('RGB', (800, 600), color=(50, 150, 50))
        img_io = io.BytesIO()
        img.save(img_io, format='JPEG')
        img_io.seek(0)

        uploaded = SimpleUploadedFile("sneakers.jpg", img_io.read(), content_type="image/jpeg")

        data = {
            'product_name': 'Running Sneakers',
            'product_code': 'SNK-001',
            'category': self.category.id,
            'brand': 'Nike',
            'unit': 'Pair',
            'batch_no': 'B01',
        }
        files = {'image': uploaded}

        form = ProductForm(data=data, files=files, organization=self.org, branch=self.branch)
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save(commit=False)
        product.organization = self.org
        product.branch = self.branch
        product.save()

        self.assertTrue(bool(product.image))
        self.assertTrue(product.image.name.endswith('.webp'))

    def test_store_product_listing_inherits_product_image(self):
        """Test ProductListing.get_image_url resolves product image for online shop"""
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from store.models import StoreListing, ProductListing

        img = Image.new('RGB', (400, 400), color=(10, 20, 30))
        img_io = io.BytesIO()
        img.save(img_io, format='JPEG')
        img_io.seek(0)

        uploaded = SimpleUploadedFile("dress.jpg", img_io.read(), content_type="image/jpeg")

        product = Product.objects.create(
            organization=self.org,
            branch=self.branch,
            product_name="Evening Gown",
            category=self.category,
            brand="Zara",
            product_code="DRS-99",
            image=uploaded
        )
        inventory = Inventory.objects.create(
            organization=self.org,
            branch=self.branch,
            product=product,
            quantity=10,
            sale_price=50000.0,
            cost_price=30000.0,
            status='Available'
        )

        store, _ = StoreListing.objects.get_or_create(organization=self.org)
        listing, _ = ProductListing.objects.get_or_create(store=store, inventory=inventory)

        self.assertIsNotNone(listing.get_image_url)
        self.assertTrue('dress' in listing.get_image_url or '.webp' in listing.get_image_url)

    def test_walk_in_store_update_cart_url_resolution(self):
        """Ensure update_cart resolves to the IMS walk-in cart URL and does not collide with online store"""
        url = reverse('update_cart', kwargs={'pk': self.branch.id})
        self.assertEqual(url, f"/ims/update_cart/{self.branch.id}/")

        user = User.objects.create_user(
            email="carttester@example.com",
            password="testpassword123",
            first_name="Cart",
            last_name="Tester"
        )
        from account.models import OrganizationMembership
        OrganizationMembership.objects.create(
            user=user,
            organization=self.org,
            branch=self.branch,
            role="owner"
        )
        self.client.login(email="carttester@example.com", password="testpassword123")

        product = Product.objects.create(
            organization=self.org,
            branch=self.branch,
            product_name="Walk-in Sneaker",
            category=self.category,
            product_code="W-SNK"
        )
        inventory = Inventory.objects.create(
            organization=self.org,
            branch=self.branch,
            product=product,
            quantity=10,
            quantity_available=10,
            sale_price=10000.0,
            cost_price=7000.0,
            status='Available'
        )

        # Test AJAX add to cart for walk-in store
        response = self.client.post(
            url,
            data=json.dumps({'inventoryId': str(inventory.id), 'action': 'add'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('qty'), 1)


class InvoiceInstallmentAndPermissionsTests(TestCase):
    def setUp(self):
        from account.models import OrganizationMembership
        self.org = Organization.objects.create(name="Invoice Org", slug="invoice-org", is_active=True)
        self.branch = Branch.objects.create(name="Main Branch", organization=self.org)
        self.org.default_branch = self.branch
        self.org.save()

        plan, _ = Plan.objects.get_or_create(
            tier='business',
            size='starter',
            billing_frequency='monthly',
            defaults={'price': Decimal('199.00'), 'has_online_store': True}
        )
        plan.has_online_store = True
        plan.save()
        Subscription.objects.create(
            organization=self.org,
            plan=plan,
            is_active=True,
            end_date=timezone.now() + timedelta(days=30)
        )

        # Create Owner, Manager, and Sales users
        self.owner = User.objects.create_user(
            email="owner@invoiceorg.com", password="password123",
            first_name="Alice", last_name="Owner", role="owner",
            organization=self.org, branch=self.branch, is_active=True
        )
        self.org.owned_by = self.owner
        self.org.save()
        OrganizationMembership.objects.create(
            user=self.owner, organization=self.org, branch=self.branch, role="owner"
        )

        self.manager = User.objects.create_user(
            email="manager@invoiceorg.com", password="password123",
            first_name="Bob", last_name="Manager", role="manager",
            organization=self.org, branch=self.branch, is_active=True
        )
        OrganizationMembership.objects.create(
            user=self.manager, organization=self.org, branch=self.branch, role="manager"
        )

        self.sales_user = User.objects.create_user(
            email="sales@invoiceorg.com", password="password123",
            first_name="Charlie", last_name="Sales", role="sales",
            organization=self.org, branch=self.branch, is_active=True
        )
        OrganizationMembership.objects.create(
            user=self.sales_user, organization=self.org, branch=self.branch, role="sales"
        )

        self.category = Category.objects.create(
            organization=self.org, branch=self.branch, category_name="Appliances"
        )
        self.product = Product.objects.create(
            organization=self.org, branch=self.branch,
            product_name="Generator", category=self.category, product_code="GEN-01"
        )
        self.inventory = Inventory.objects.create(
            organization=self.org, branch=self.branch, product=self.product,
            quantity=10, quantity_available=10, cost_price=100.0, sale_price=200.0, status="Available"
        )

    def test_installment_flow_and_first_payment_inventory_deduction(self):
        from ims.models import Invoice, InvoicePayment, InvoiceEditLog
        self.client.login(email="manager@invoiceorg.com", password="password123")

        # 1. Manager creates an installment invoice for 3 units @ 200 = 600
        resp = self.client.post(reverse('create_invoice', kwargs={'pk': self.branch.id}), {
            'customer_name': 'John Installment',
            'customer_phone': '08011122233',
            'payment_plan': 'installment',
            'payment_method': 'Transfer',
            'inventory_id[]': [str(self.inventory.id)],
            'quantity[]': ['3'],
        })
        self.assertEqual(resp.status_code, 302)
        invoice = Invoice.objects.get(customer_name='John Installment')
        self.assertEqual(invoice.payment_plan, 'installment')
        self.assertEqual(invoice.status, 'pending')
        self.assertEqual(invoice.total_amount, 600.0)
        self.assertEqual(invoice.balance_due, 600.0)
        self.assertFalse(invoice.inventory_deducted)

        # Inventory is still 10 before first installment
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)

        # 2. First installment payment of 250 -> deducts inventory, status becomes partially_paid
        resp = self.client.post(reverse('confirm_payment', kwargs={'pk': invoice.id}), {
            'amount_paid': '250',
            'payment_method': 'Transfer',
            'payment_notes': 'First installment',
        })
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'partially_paid')
        self.assertEqual(invoice.amount_paid, 250.0)
        self.assertEqual(invoice.balance_due, 350.0)
        self.assertTrue(invoice.inventory_deducted)

        # Inventory deducted on first installment (10 - 3 = 7)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 7)
        # Sale record is not created until payment is complete
        self.assertEqual(Sale.objects.filter(branch=self.branch).count(), 0)

        # 3. Second installment payment of 150 -> inventory NOT deducted again, status still partially_paid
        resp = self.client.post(reverse('confirm_payment', kwargs={'pk': invoice.id}), {
            'amount_paid': '150',
            'payment_method': 'Cash',
            'payment_notes': 'Second installment',
        })
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'partially_paid')
        self.assertEqual(invoice.amount_paid, 400.0)
        self.assertEqual(invoice.balance_due, 200.0)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 7)

        # 4. Final installment payment of 200 -> status becomes paid, Sale record created
        resp = self.client.post(reverse('confirm_payment', kwargs={'pk': invoice.id}), {
            'amount_paid': '200',
            'payment_method': 'POS',
            'payment_notes': 'Final installment',
        })
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'paid')
        self.assertEqual(invoice.amount_paid, 600.0)
        self.assertEqual(invoice.balance_due, 0.0)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 7)
        self.assertEqual(InvoicePayment.objects.filter(invoice=invoice).count(), 3)
        self.assertEqual(Sale.objects.filter(branch=self.branch, completed=True).count(), 1)

    def test_role_permissions_and_owner_edit_log(self):
        from ims.models import Invoice, InvoiceEditLog
        # Sales user cannot create invoices
        self.client.login(email="sales@invoiceorg.com", password="password123")
        resp = self.client.get(reverse('create_invoice', kwargs={'pk': self.branch.id}))
        self.assertEqual(resp.status_code, 302)

        # Manager can create and edit invoices
        self.client.login(email="manager@invoiceorg.com", password="password123")
        self.client.post(reverse('create_invoice', kwargs={'pk': self.branch.id}), {
            'customer_name': 'Mary Client',
            'payment_plan': 'one_time',
            'inventory_id[]': [str(self.inventory.id)],
            'quantity[]': ['2'],
        })
        invoice = Invoice.objects.get(customer_name='Mary Client')

        # Manager edits the invoice
        self.client.post(reverse('edit_invoice', kwargs={'pk': invoice.id}), {
            'customer_name': 'Mary Updated',
            'customer_phone': '09099988877',
            'payment_plan': 'installment',
            'inventory_id[]': [str(self.inventory.id)],
            'quantity[]': ['4'],
        })
        invoice.refresh_from_db()
        self.assertEqual(invoice.customer_name, 'Mary Updated')
        self.assertEqual(invoice.payment_plan, 'installment')
        self.assertEqual(invoice.total_amount, 800.0)

        # Edit log recorded with manager's info
        logs = InvoiceEditLog.objects.filter(invoice=invoice, action='edited')
        self.assertEqual(logs.count(), 1)
        self.assertIn("Bob Manager", logs.first().summary)
        self.assertIn("Mary Updated", logs.first().summary)

        # Manager CANNOT delete the invoice
        del_resp = self.client.post(reverse('delete_invoice', kwargs={'pk': invoice.id}))
        self.assertTrue(Invoice.objects.filter(id=invoice.id).exists())

        # Owner CAN see the edit log on invoice_detail and CAN delete the invoice
        self.client.login(email="owner@invoiceorg.com", password="password123")
        detail_resp = self.client.get(reverse('invoice_detail', kwargs={'pk': invoice.id}))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, "Owner Audit Log")
        self.assertContains(detail_resp, "Bob Manager")

        del_owner_resp = self.client.post(reverse('delete_invoice', kwargs={'pk': invoice.id}))
        self.assertEqual(del_owner_resp.status_code, 302)
        self.assertFalse(Invoice.objects.filter(id=invoice.id).exists())

    def test_storefront_hides_inventory_quantities(self):
        from store.models import StoreListing, ProductListing
        store, _ = StoreListing.objects.get_or_create(organization=self.org, defaults={'is_active': True})
        listing, _ = ProductListing.objects.get_or_create(store=store, inventory=self.inventory, defaults={'is_visible': True})

        sf_resp = self.client.get(reverse('storefront', kwargs={'org_slug': self.org.slug}))
        self.assertEqual(sf_resp.status_code, 200)
        self.assertContains(sf_resp, "In Stock")
        self.assertNotContains(sf_resp, f"In Stock ({self.inventory.quantity})")

        pd_resp = self.client.get(reverse('product_detail', kwargs={'org_slug': self.org.slug, 'listing_id': listing.id}))
        self.assertEqual(pd_resp.status_code, 200)
        self.assertContains(pd_resp, "In Stock")
        self.assertNotContains(pd_resp, f"{self.inventory.quantity} in stock")

    def test_closed_invoice_cannot_be_edited_until_owner_reopens(self):
        from ims.models import Invoice, InvoiceEditLog
        self.client.login(email="manager@invoiceorg.com", password="password123")
        self.client.post(reverse('create_invoice', kwargs={'pk': self.branch.id}), {
            'customer_name': 'Closed Test Customer',
            'payment_plan': 'one_time',
            'inventory_id[]': [str(self.inventory.id)],
            'quantity[]': ['1'],
        })
        invoice = Invoice.objects.get(customer_name='Closed Test Customer')

        # Close the invoice
        self.client.post(reverse('close_invoice', kwargs={'pk': invoice.id}))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'closed')

        # Attempt to edit while closed -> blocked
        self.client.post(reverse('edit_invoice', kwargs={'pk': invoice.id}), {
            'customer_name': 'Should Not Update',
            'payment_plan': 'one_time',
            'inventory_id[]': [str(self.inventory.id)],
            'quantity[]': ['2'],
        })
        invoice.refresh_from_db()
        self.assertEqual(invoice.customer_name, 'Closed Test Customer')

        # Manager cannot reopen the invoice
        self.client.post(reverse('reopen_invoice', kwargs={'pk': invoice.id}))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'closed')

        # Owner can reopen the invoice
        self.client.login(email="owner@invoiceorg.com", password="password123")
        self.client.post(reverse('reopen_invoice', kwargs={'pk': invoice.id}))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'pending')
        self.assertTrue(InvoiceEditLog.objects.filter(invoice=invoice, action='reopened').exists())

        # Now editing succeeds
        self.client.post(reverse('edit_invoice', kwargs={'pk': invoice.id}), {
            'customer_name': 'Reopened And Edited',
            'payment_plan': 'one_time',
            'inventory_id[]': [str(self.inventory.id)],
            'quantity[]': ['2'],
        })
        invoice.refresh_from_db()
        self.assertEqual(invoice.customer_name, 'Reopened And Edited')

    def test_supplier_restock_request_with_three_pocs_optional_pocs_and_direct_restock(self):
        from django.core import mail
        from ims.models import RestockRequest, Product, Inventory
        import json

        # Create a second product & inventory in the branch
        product2 = Product.objects.create(
            organization=self.org,
            branch=self.branch,
            product_name="USB-C Dock",
            category=self.category,
            product_code="DOCK-002",
            unit="pcs"
        )
        inventory2 = Inventory.objects.create(
            organization=self.org,
            branch=self.branch,
            product=product2,
            quantity=5,
            cost_price=200.0,
            sale_price=350.0,
            status="Available"
        )

        # 1. Manager requests restock with 3 POC emails
        self.client.login(email="manager@invoiceorg.com", password="password123")
        mail.outbox = []
        resp = self.client.post(reverse('create_restock_request', kwargs={'pk': self.branch.id}), {
            'supplier_name': 'Global Tech Vendors',
            'vendor_email': ['poc1@vendor.com', 'poc2@vendor.com', 'poc3@vendor.com'],
            'items_json': json.dumps([
                {'inventory_id': str(self.inventory.id), 'quantity': 15},
                {'inventory_id': str(inventory2.id), 'quantity': 8},
            ]),
            'notes': 'Urgent branch restock',
        })
        self.assertEqual(resp.status_code, 302)

        req = RestockRequest.objects.get(supplier_name='Global Tech Vendors')
        self.assertEqual(req.email_list, ['poc1@vendor.com', 'poc2@vendor.com', 'poc3@vendor.com'])
        self.assertTrue(req.email_sent)
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, ['poc1@vendor.com', 'poc2@vendor.com', 'poc3@vendor.com'])
        # PDF attachment + download link included
        self.assertEqual(len(sent_email.attachments), 1)
        self.assertTrue(sent_email.attachments[0][0].endswith('.pdf'))
        self.assertIn(reverse('restock_request_pdf', kwargs={'pk': req.id}), sent_email.body)

        # Saved POC emails on product
        self.product.refresh_from_db()
        self.assertEqual(self.product.supplier_email_list, ['poc1@vendor.com', 'poc2@vendor.com', 'poc3@vendor.com'])

        # 2. External supplier can download the PDF without login
        self.client.logout()
        pdf_resp = self.client.get(reverse('restock_request_pdf', kwargs={'pk': req.id}))
        self.assertEqual(pdf_resp.status_code, 200)
        self.assertEqual(pdf_resp['Content-Type'], 'application/pdf')

        # 3. Manager ticks the first item supplied and clicks Restock Directly
        self.client.login(email="manager@invoiceorg.com", password="password123")
        items = list(req.items.order_by('quantity_requested'))
        item_dock = [i for i in items if i.inventory_id == inventory2.id][0]
        item_laptop = [i for i in items if i.inventory_id == self.inventory.id][0]

        self.client.post(reverse('fulfill_restock_request', kwargs={'pk': req.id}), {
            'item_ids': [str(item_dock.id)],
            f'quantity_supplied_{item_dock.id}': '8',
        })
        req.refresh_from_db()
        inventory2.refresh_from_db()
        item_dock.refresh_from_db()
        self.assertEqual(req.status, 'partially_supplied')
        self.assertTrue(item_dock.is_restocked)
        self.assertEqual(inventory2.quantity, 5 + 8)

        # 4. Owner ticks the remaining item supplied -> status becomes 'completed'
        self.client.login(email="owner@invoiceorg.com", password="password123")
        self.client.post(reverse('fulfill_restock_request', kwargs={'pk': req.id}), {
            'item_ids': [str(item_laptop.id)],
            f'quantity_supplied_{item_laptop.id}': '15',
        })
        req.refresh_from_db()
        self.inventory.refresh_from_db()
        self.assertEqual(req.status, 'completed')
        self.assertEqual(self.inventory.quantity, 10 + 15)

        # 5. Requesting restock with 0 POC emails (optional) and 1 POC email
        mail.outbox = []
        self.client.post(reverse('create_restock_request', kwargs={'pk': self.branch.id}), {
            'supplier_name': 'Local Walk-In Vendor',
            'vendor_email': [''],
            'inventory_id': [str(self.inventory.id)],
            'quantity_requested': ['5'],
        })
        req_no_email = RestockRequest.objects.get(supplier_name='Local Walk-In Vendor')
        self.assertEqual(req_no_email.email_list, [])
        self.assertFalse(req_no_email.email_sent)
        self.assertEqual(len(mail.outbox), 0)

    def test_supplier_quote_link_owner_price_approval_and_apply_on_restock(self):
        from django.core import mail
        from ims.models import RestockRequest

        # Ensure initial inventory prices
        self.inventory.cost_price = 400.0
        self.inventory.sale_price = 500.0
        self.inventory.quantity = 10
        self.inventory.save()

        # 1. Manager creates restock request with 2 POC emails
        self.client.login(email="manager@invoiceorg.com", password="password123")
        mail.outbox = []
        self.client.post(reverse('create_restock_request', kwargs={'pk': self.branch.id}), {
            'supplier_name': 'Price Quote Vendor',
            'vendor_email': ['poc1@quotevendor.com', 'poc2@quotevendor.com'],
            'inventory_id': [str(self.inventory.id)],
            'quantity_requested': ['15'],
        })
        req = RestockRequest.objects.get(supplier_name='Price Quote Vendor')
        item = req.items.first()

        # Email contains supplier quote link
        quote_path = reverse('supplier_restock_quote', kwargs={'pk': req.id})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(quote_path, mail.outbox[0].body)

        # 2. Supplier visits public quote page (unauthenticated) and submits cost price & available qty
        self.client.logout()
        get_quote_resp = self.client.get(quote_path)
        self.assertEqual(get_quote_resp.status_code, 200)
        self.assertContains(get_quote_resp, self.product.product_name)

        post_quote_resp = self.client.post(quote_path, {
            'quote_submitted_by_name': 'Jane POC',
            'quote_submitted_by_email': 'poc2@quotevendor.com',
            'supplier_quote_notes': 'Can supply 12 units at new price',
            f'quoted_quantity_{item.id}': '12',
            f'quoted_cost_price_{item.id}': '550.00',
        })
        self.assertEqual(post_quote_resp.status_code, 302)

        req.refresh_from_db()
        item.refresh_from_db()
        self.assertTrue(req.quote_submitted)
        self.assertEqual(req.quote_submitted_by_email, 'poc2@quotevendor.com')
        self.assertEqual(req.quote_submitted_by_name, 'Jane POC')
        self.assertEqual(item.quoted_cost_price, 550.0)
        self.assertEqual(item.quoted_quantity, 12)
        self.assertEqual(item.price_status, 'quoted')

        # 3. Manager cannot approve prices (Owner only)
        self.client.login(email="manager@invoiceorg.com", password="password123")
        self.client.post(reverse('approve_restock_item_prices', kwargs={'pk': req.id}), {
            f'approved_cost_price_{item.id}': '550.00',
            f'new_sale_price_{item.id}': '750.00',
        })
        item.refresh_from_db()
        self.assertEqual(item.price_status, 'quoted')

        # 4. Owner accepts the new cost price (550) and sets new sale price (750)
        self.client.login(email="owner@invoiceorg.com", password="password123")
        self.client.post(reverse('approve_restock_item_prices', kwargs={'pk': req.id}), {
            f'approved_cost_price_{item.id}': '550.00',
            f'new_sale_price_{item.id}': '750.00',
        })
        item.refresh_from_db()
        self.inventory.refresh_from_db()
        self.assertEqual(item.price_status, 'accepted')
        self.assertEqual(item.approved_cost_price, 550.0)
        self.assertEqual(item.new_sale_price, 750.0)
        # Before delivery/restock, live Inventory still holds the old cost & sale price!
        self.assertEqual(self.inventory.cost_price, 400.0)
        self.assertEqual(self.inventory.sale_price, 500.0)

        # 5. Manager (or Owner) ticks item and clicks Restock Directly -> Inventory quantity, cost_price, sale_price, and profit all update!
        self.client.login(email="manager@invoiceorg.com", password="password123")
        self.client.post(reverse('fulfill_restock_request', kwargs={'pk': req.id}), {
            'item_ids': [str(item.id)],
            f'quantity_supplied_{item.id}': '12',
        })
        self.inventory.refresh_from_db()
        self.product.refresh_from_db()
        req.refresh_from_db()
        self.assertEqual(req.status, 'completed')
        self.assertEqual(self.inventory.quantity, 10 + 12)
        self.assertEqual(self.inventory.cost_price, 550.0)
        self.assertEqual(self.inventory.sale_price, 750.0)
        self.assertEqual(self.product.profit, 200.0)




