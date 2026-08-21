from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse
from account.models import Organization, Branch, CustomUser
from ims.models import Category, Product, Inventory, APIKey
from subscriptions.models import Subscription, Plan
import json

class InventoryAPITestCase(TestCase):
    def setUp(self):
        # 1. Create Organization & Branch
        self.org = Organization.objects.create(
            name="Bobby's Place",
            slug="bobbys-place"
        )
        self.branch = Branch.objects.create(
            organization=self.org,
            name="HQ",
            address="Lagos"
        )
        
        # 2. Get or Create Plan & Active Subscription
        self.plan, _ = Plan.objects.get_or_create(
            tier="growth",
            size="starter",
            billing_frequency="monthly",
            defaults={
                'name': "Growth Plan",
                'price': 15000.00,
                'duration_in_days': 30
            }
        )
        self.subscription = Subscription.objects.create(
            organization=self.org,
            plan=self.plan,
            start_date=timezone.now() - timezone.timedelta(days=1),
            end_date=timezone.now() + timezone.timedelta(days=29),
            is_active=True
        )

        # 3. Create Inventory Items
        self.category = Category.objects.create(
            organization=self.org,
            branch=self.branch,
            category_name="Electronics"
        )
        self.product = Product.objects.create(
            organization=self.org,
            branch=self.branch,
            product_name="Wireless Mouse",
            product_code="WM-001",
            category=self.category
        )
        self.inventory = Inventory.objects.create(
            organization=self.org,
            branch=self.branch,
            product=self.product,
            quantity=20,
            quantity_available=15,
            reorder_level=5,
            sale_price=4500.00,
            cost_price=3000.00,
            status="Available"
        )

        # 4. Create API Key
        self.api_key = APIKey.objects.create(
            organization=self.org,
            name="Default Bot Key",
            key="qs_live_test_key_123456",
            is_active=True
        )
        
        self.client = Client()

    def test_status_endpoint_with_valid_key(self):
        """
        Request with a valid API key and active subscription succeeds.
        """
        url = reverse('api_inventory_status')
        response = self.client.get(url, HTTP_X_API_KEY=self.api_key.key)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['metrics']['total_skus'], 1)
        self.assertEqual(data['metrics']['in_stock'], 1)

    def test_status_endpoint_with_missing_key(self):
        """
        Request with missing credentials returns 401.
        """
        url = reverse('api_inventory_status')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)
        self.assertIn('error', response.json())

    def test_status_endpoint_with_invalid_key(self):
        """
        Request with a non-existent key returns 401.
        """
        url = reverse('api_inventory_status')
        response = self.client.get(url, HTTP_X_API_KEY="qs_live_fake_key")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error'], 'Invalid API Key')

    def test_status_endpoint_with_inactive_key(self):
        """
        Request with an inactive key returns 401.
        """
        self.api_key.is_active = False
        self.api_key.save()
        
        url = reverse('api_inventory_status')
        response = self.client.get(url, HTTP_X_API_KEY=self.api_key.key)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error'], 'API Key is inactive or revoked')

    def test_status_endpoint_with_expired_subscription(self):
        """
        Request from an organization with expired subscription returns 403.
        """
        self.subscription.end_date = timezone.now() - timezone.timedelta(days=1)
        self.subscription.save()

        url = reverse('api_inventory_status')
        response = self.client.get(url, HTTP_X_API_KEY=self.api_key.key)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'Active subscription is required to access the API')

    def test_product_list_endpoint(self):
        """
        Product list returns details of inventories.
        """
        url = reverse('api_product_list')
        response = self.client.get(url, HTTP_X_API_KEY=self.api_key.key)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['products'][0]['product_code'], 'WM-001')

    def test_product_query_endpoint(self):
        """
        Query product details by code or name search query parameters.
        """
        url = reverse('api_product_detail')
        # Code search
        response = self.client.get(f"{url}?code=WM-001", HTTP_X_API_KEY=self.api_key.key)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['matches'][0]['product_name'], 'Wireless Mouse')

        # Name query search
        response = self.client.get(f"{url}?query=Mouse", HTTP_X_API_KEY=self.api_key.key)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)

    def test_status_endpoint_with_developer_sandbox_bypasses_subscription(self):
        """
        An organization with business_type='developer' can access the API even
        if they do not have an active/valid subscription.
        """
        # Deactivate subscription
        self.subscription.is_active = False
        self.subscription.save()

        # Mark organization as developer sandbox
        self.org.business_type = 'developer'
        self.org.save()

        url = reverse('api_inventory_status')
        response = self.client.get(url, HTTP_X_API_KEY=self.api_key.key)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
