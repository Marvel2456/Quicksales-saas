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
