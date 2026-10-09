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

