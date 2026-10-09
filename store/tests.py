import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from account.models import Organization, Branch, CustomUser, OrganizationMembership
from ims.models import Category, Product, Inventory, Sale
from ims.services.sales import SalesService
from subscriptions.models import Plan, Subscription
from store.models import (
    StoreListing, ProductListing, StoreDiscount, OnlineOrder,
    OnlineOrderItem, Buyer, StoreBankAccount, StorePayout
)
from store.views import complete_order_sale
from store.vendor_views import calculate_organization_balances, request_organization_payout


class OnlineStoreFeatureTests(TestCase):
    def setUp(self):
        # Create user & organization
        self.user = CustomUser.objects.create_user(
            email='vendor@test.com',
            password='Password123!',
            first_name='Vendor',
            last_name='Owner',
            role='owner'
        )
        self.org = Organization.objects.create(
            name='Test Fashion Store',
            slug='test-fashion-store',
            country='Nigeria',
            owned_by=self.user,
            is_active=True,
            trial_start=timezone.now(),
            trial_end=timezone.now() + timezone.timedelta(days=30)
        )
        # Create Branch
        self.branch = Branch.objects.create(
            organization=self.org,
            name='Lagos Flagship',
            address='12 Marina St, Lagos'
        )
        # Create membership
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            branch=self.branch,
            role='owner',
            is_active=True
        )
        self.user.organization = self.org
        self.user.branch = self.branch
        self.user.save()

        # Create active subscription for test org
        plan, _ = Plan.objects.get_or_create(
            tier='growth',
            size='starter',
            billing_frequency='monthly',
            defaults={
                'name': 'Standard Plan',
                'price': Decimal('10000.00'),
                'duration_in_days': 30
            }
        )
        Subscription.objects.create(
            organization=self.org,
            plan=plan,
            provider='paystack',
            currency='NGN',
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=30),
            is_active=True
        )

        # Default branch auto-assignment
        self.org.refresh_from_db()
        if not self.org.default_branch:
            self.org.default_branch = self.branch
            self.org.save()

        # Create Category & Product & Inventory
        self.category = Category.objects.create(
            organization=self.org,
            branch=self.branch,
            category_name='Dresses'
        )
        self.product = Product.objects.create(
            organization=self.org,
            branch=self.branch,
            product_name='Silk Summer Dress',
            category=self.category,
            product_code='DRS-001'
        )
        self.inventory = Inventory.objects.create(
            organization=self.org,
            branch=self.branch,
            product=self.product,
            quantity=20,
            quantity_available=20,
            cost_price=8000.00,
            sale_price=15000.00,
            status='Available'
        )

        # Create StoreListing & ProductListing
        self.store, _ = StoreListing.objects.get_or_create(
            organization=self.org,
            defaults={'branch': self.branch, 'is_active': True, 'tagline': 'Luxury African Fashion'}
        )
        self.listing, _ = ProductListing.objects.get_or_create(
            store=self.store,
            inventory=self.inventory,
            defaults={'is_visible': True, 'featured': True}
        )
        self.listing.featured = True
        self.listing.save()

        self.client = Client()

    def test_default_branch_auto_sync(self):
        """Test default branch auto-sync on store listing"""
        self.assertEqual(self.store.get_active_branch(), self.branch)

    def test_buyer_registration_and_auth(self):
        """Test buyer signup, password hashing, and authentication"""
        buyer = Buyer.objects.create(
            email='buyer@gmail.com',
            first_name='Amaka',
            last_name='Eze',
            phone_number='08012345678'
        )
        buyer.set_password('Secret123!')
        buyer.save()

        self.assertTrue(buyer.check_password('Secret123!'))
        self.assertFalse(buyer.check_password('WrongPassword'))
        self.assertEqual(buyer.get_full_name(), 'Amaka Eze')

    def test_store_discount_validation(self):
        """Test discount validation, usage capping, and date checking"""
        discount = StoreDiscount.objects.create(
            organization=self.org,
            branch=self.branch,
            code='PROMO20',
            discount_type='percent',
            value=Decimal('20.00'),
            max_uses=2,
            uses=0,
            is_active=True
        )
        self.assertTrue(discount.is_valid())

        # Test usage cap
        discount.uses = 2
        self.assertFalse(discount.is_valid())

    def test_public_storefront_view(self):
        """Test public storefront renders 200 OK and lists products"""
        url = reverse('storefront', kwargs={'org_slug': self.org.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Silk Summer Dress')
        self.assertContains(response, 'Test Fashion Store')

    def test_product_detail_view(self):
        """Test single product detail page renders properly"""
        url = reverse('product_detail', kwargs={'org_slug': self.org.slug, 'listing_id': self.listing.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Silk Summer Dress')
        self.assertContains(response, '15,000')

    def test_cart_add_and_checkout_flow(self):
        """Test adding item to bag and placing order"""
        add_url = reverse('store_add_to_cart', kwargs={'org_slug': self.org.slug})
        add_res = self.client.post(
            add_url,
            data={'listing_id': str(self.listing.id), 'quantity': 2},
            content_type='application/json'
        )
        self.assertEqual(add_res.status_code, 200)
        self.assertEqual(add_res.json()['cart_count'], 2)

        # Place order
        checkout_url = reverse('store_checkout', kwargs={'org_slug': self.org.slug})
        order_res = self.client.post(checkout_url, {
            'place_order': '1',
            'buyer_name': 'Amaka Eze',
            'buyer_email': 'amaka@test.com',
            'buyer_phone': '08099887766',
            'shipping_address': '15 Victoria Island, Lagos'
        })
        self.assertEqual(order_res.status_code, 302)

        # Verify order was created in DB
        order = OnlineOrder.objects.filter(organization=self.org).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.buyer_name, 'Amaka Eze')
        self.assertEqual(order.status, 'pending')
        self.assertEqual(order.total_amount, Decimal('30000.00'))
        self.assertEqual(order.items.count(), 1)

    def test_order_confirmation_deducts_inventory(self):
        """Test vendor confirming order creates IMS Sale and deducts stock"""
        order = OnlineOrder.objects.create(
            organization=self.org,
            branch=self.branch,
            buyer_name='Amaka Eze',
            buyer_email='amaka@test.com',
            buyer_phone='08099887766',
            subtotal=Decimal('30000.00'),
            total_amount=Decimal('30000.00'),
            status='pending'
        )
        OnlineOrderItem.objects.create(
            order=order,
            product_listing=self.listing,
            inventory=self.inventory,
            product_name=self.listing.display_title,
            unit_price=Decimal('15000.00'),
            quantity=2,
            total_price=Decimal('30000.00')
        )

        self.client.force_login(self.user)
        confirm_url = reverse('vendor_order_detail', kwargs={'order_id': order.id})
        res = self.client.post(confirm_url, {'action': 'confirm'})
        self.assertEqual(res.status_code, 302)

        order.refresh_from_db()
        self.inventory.refresh_from_db()
        self.assertEqual(order.status, 'confirmed')
        self.assertIsNotNone(order.sale)
        # Stock should be 20 - 2 = 18
        self.assertEqual(self.inventory.quantity_available, 18)

    def test_order_cancel_restores_inventory(self):
        """Test cancelling a confirmed order restores inventory stock"""
        order = OnlineOrder.objects.create(
            organization=self.org,
            branch=self.branch,
            buyer_name='Chioma Obi',
            buyer_email='chioma@test.com',
            subtotal=Decimal('15000.00'),
            total_amount=Decimal('15000.00'),
            status='pending'
        )
        OnlineOrderItem.objects.create(
            order=order,
            product_listing=self.listing,
            inventory=self.inventory,
            product_name=self.listing.display_title,
            unit_price=Decimal('15000.00'),
            quantity=3,
            total_price=Decimal('45000.00')
        )
        # Complete sale first -> stock becomes 20 - 3 = 17
        complete_order_sale(order)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity_available, 17)

        # Cancel order via vendor action
        self.client.force_login(self.user)
        url = reverse('vendor_order_detail', kwargs={'order_id': order.id})
        res = self.client.post(url, {'action': 'cancel', 'cancelled_reason': 'Customer requested refund'})
        self.assertEqual(res.status_code, 302)

        order.refresh_from_db()
        self.inventory.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        self.assertEqual(self.inventory.quantity_available, 20)

    def test_online_sale_rep_display_and_filter(self):
        """Test that online sales display 'Online' as sales rep and are filterable by 'Online'"""
        order = OnlineOrder.objects.create(
            organization=self.org,
            branch=self.branch,
            buyer_name='Emeka Nnamdi',
            buyer_email='emeka@test.com',
            subtotal=Decimal('15000.00'),
            total_amount=Decimal('15000.00'),
            status='pending'
        )
        OnlineOrderItem.objects.create(
            order=order,
            product_listing=self.listing,
            inventory=self.inventory,
            product_name=self.listing.display_title,
            unit_price=Decimal('15000.00'),
            quantity=1,
            total_price=Decimal('15000.00')
        )
        sale = complete_order_sale(order)
        self.assertIsNotNone(sale)
        self.assertEqual(sale.sales_rep_name, "Online")

        # Test SalesService filtering by rep='Online'
        filtered_sales = SalesService.get_sales_summary(self.org, rep='Online')
        self.assertIn(sale, filtered_sales)

        # Non-matching staff search should exclude online sale
        filtered_other = SalesService.get_sales_summary(self.org, rep='NonExistentRep')
        self.assertNotIn(sale, filtered_other)


class IdempotencyAndConcurrencyTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='idemp_owner@test.com',
            password='Password123!',
            first_name='Idemp',
            last_name='Vendor',
            role='owner'
        )
        self.org = Organization.objects.create(
            name='Idempotency Test Store',
            slug='idemp-test-store',
            owned_by=self.user,
            is_active=True
        )
        self.branch = Branch.objects.create(
            organization=self.org,
            name='Main Branch',
            address='Lagos'
        )
        self.org.default_branch = self.branch
        self.org.save()

        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            branch=self.branch,
            role='owner',
            is_active=True
        )

        plan, _ = Plan.objects.get_or_create(
            tier='growth',
            size='starter',
            billing_frequency='monthly',
            defaults={'price': Decimal('10000.00'), 'duration_in_days': 30}
        )
        Subscription.objects.create(
            organization=self.org,
            plan=plan,
            provider='paystack',
            currency='NGN',
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=30),
            is_active=True
        )

        self.category = Category.objects.create(
            organization=self.org,
            branch=self.branch,
            category_name='Gadgets'
        )
        self.product = Product.objects.create(
            organization=self.org,
            branch=self.branch,
            product_name='Smart Watch',
            category=self.category,
            product_code='WAT-001'
        )
        self.inventory = Inventory.objects.create(
            organization=self.org,
            branch=self.branch,
            product=self.product,
            quantity=10,
            quantity_available=10,
            cost_price=20000.00,
            sale_price=35000.00,
            status='Available'
        )
        self.store, _ = StoreListing.objects.get_or_create(
            organization=self.org,
            defaults={'branch': self.branch, 'is_active': True}
        )
        self.listing, _ = ProductListing.objects.get_or_create(
            store=self.store,
            inventory=self.inventory,
            defaults={'is_visible': True}
        )

    def test_complete_order_sale_idempotency_prevents_double_deduction(self):
        """Calling complete_order_sale multiple times returns same Sale and deducts stock only once"""
        order = OnlineOrder.objects.create(
            organization=self.org,
            branch=self.branch,
            buyer_name='Tunde Ade',
            buyer_email='tunde@test.com',
            subtotal=Decimal('70000.00'),
            total_amount=Decimal('70000.00'),
            status='pending'
        )
        OnlineOrderItem.objects.create(
            order=order,
            product_listing=self.listing,
            inventory=self.inventory,
            product_name='Smart Watch',
            unit_price=Decimal('35000.00'),
            quantity=2,
            total_price=Decimal('70000.00')
        )

        # Call complete_order_sale 3 consecutive times (simulating duplicate webhook / callback / confirm calls)
        sale1 = complete_order_sale(order)
        sale2 = complete_order_sale(order)
        sale3 = complete_order_sale(order)

        self.assertEqual(sale1.id, sale2.id)
        self.assertEqual(sale2.id, sale3.id)

        # Total sales created for this org should be exactly 1
        self.assertEqual(Sale.objects.filter(organization=self.org).count(), 1)

        # Inventory should be deducted exactly once: 10 - 2 = 8
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 8)
        self.assertEqual(self.inventory.quantity_available, 8)

    def test_withdrawal_available_balance_calculation(self):
        """Verifies calculation of gross revenue, completed payouts, pending payouts, and available balance"""
        # Create 2 paid orders of ₦50,000 each = ₦100,000 gross
        for i in range(2):
            OnlineOrder.objects.create(
                organization=self.org,
                branch=self.branch,
                buyer_name=f'Buyer {i}',
                buyer_email=f'b{i}@test.com',
                subtotal=Decimal('50000.00'),
                total_amount=Decimal('50000.00'),
                payment_status='paid',
                status='confirmed'
            )

        # Create 1 completed payout of ₦20,000
        StorePayout.objects.create(
            organization=self.org,
            amount=Decimal('20000.00'),
            bank_name='Access Bank',
            account_number='0123456789',
            account_name='Vendor Acct',
            status='completed',
            requested_by=self.user
        )

        # Create 1 pending payout of ₦15,000
        StorePayout.objects.create(
            organization=self.org,
            amount=Decimal('15000.00'),
            bank_name='Access Bank',
            account_number='0123456789',
            account_name='Vendor Acct',
            status='pending',
            requested_by=self.user
        )

        balances = calculate_organization_balances(self.org)
        self.assertEqual(balances['total_gross_revenue'], Decimal('100000.00'))
        self.assertEqual(balances['completed_payouts'], Decimal('20000.00'))
        self.assertEqual(balances['pending_payouts'], Decimal('15000.00'))
        # Available = 100,000 - 20,000 - 15,000 = 65,000
        self.assertEqual(balances['available_balance'], Decimal('65000.00'))

    def test_withdrawal_race_condition_double_spending_prevention(self):
        """
        Simulates two concurrent withdrawal requests competing for the same balance.
        If available balance is ₦50,000, two requests of ₦40,000 each must not both succeed.
        """
        # Bank details setup
        StoreBankAccount.objects.create(
            organization=self.org,
            bank_name='Zenith Bank',
            account_number='1002003004',
            account_name='Idemp Owner Ent'
        )

        # Create 1 paid order of ₦50,000
        OnlineOrder.objects.create(
            organization=self.org,
            branch=self.branch,
            buyer_name='Buyer Alpha',
            buyer_email='alpha@test.com',
            subtotal=Decimal('50000.00'),
            total_amount=Decimal('50000.00'),
            payment_status='paid',
            status='confirmed'
        )

        # First withdrawal request of ₦40,000 -> Should SUCCEED
        success1, msg1, payout1 = request_organization_payout(self.org, self.user, Decimal('40000.00'), notes='WD 1')
        self.assertTrue(success1)
        self.assertIsNotNone(payout1)

        # Second withdrawal request of ₦40,000 -> Should FAIL due to insufficient remaining balance (₦10,000 left)
        success2, msg2, payout2 = request_organization_payout(self.org, self.user, Decimal('40000.00'), notes='WD 2')
        self.assertFalse(success2)
        self.assertIn("exceeds your available balance", msg2)
        self.assertIsNone(payout2)

        # Verify only 1 payout record was created
        self.assertEqual(StorePayout.objects.filter(organization=self.org).count(), 1)


class SecurityAndIsolationTests(TestCase):
    def setUp(self):
        # Organization 1 & User 1 (Owner)
        self.user1 = CustomUser.objects.create_user(
            email='owner1@org1.com',
            password='Password123!',
            first_name='Owner',
            last_name='One',
            role='owner'
        )
        self.org1 = Organization.objects.create(
            name='Org One Store',
            slug='org-one',
            owned_by=self.user1,
            is_active=True
        )
        self.branch1 = Branch.objects.create(organization=self.org1, name='Branch 1')
        self.org1.default_branch = self.branch1
        self.org1.save()
        OrganizationMembership.objects.create(
            user=self.user1, organization=self.org1, branch=self.branch1, role='owner', is_active=True
        )

        # Organization 2 & User 2 (Owner)
        self.user2 = CustomUser.objects.create_user(
            email='owner2@org2.com',
            password='Password123!',
            first_name='Owner',
            last_name='Two',
            role='owner'
        )
        self.org2 = Organization.objects.create(
            name='Org Two Store',
            slug='org-two',
            owned_by=self.user2,
            is_active=True
        )
        self.branch2 = Branch.objects.create(organization=self.org2, name='Branch 2')
        self.org2.default_branch = self.branch2
        self.org2.save()
        OrganizationMembership.objects.create(
            user=self.user2, organization=self.org2, branch=self.branch2, role='owner', is_active=True
        )

        # Subscriptions
        plan, _ = Plan.objects.get_or_create(
            tier='growth', size='starter', billing_frequency='monthly',
            defaults={'price': Decimal('10000.00'), 'duration_in_days': 30}
        )
        Subscription.objects.create(
            organization=self.org1, plan=plan, is_active=True,
            start_date=timezone.now(), end_date=timezone.now() + timezone.timedelta(days=30)
        )
        Subscription.objects.create(
            organization=self.org2, plan=plan, is_active=True,
            start_date=timezone.now(), end_date=timezone.now() + timezone.timedelta(days=30)
        )

        # Order in Org 1
        self.order1 = OnlineOrder.objects.create(
            organization=self.org1,
            branch=self.branch1,
            buyer_name='Secret Customer',
            buyer_email='secret@gmail.com',
            total_amount=Decimal('45000.00'),
            status='pending'
        )

        self.client = Client()

    def test_cross_tenant_order_access_prevented(self):
        """User from Org 2 cannot view or access order from Org 1 (returns 404)"""
        self.client.force_login(self.user2)
        url = reverse('vendor_order_detail', kwargs={'order_id': self.order1.id})
        res = self.client.get(url)
        self.assertEqual(res.status_code, 404)

    def test_cross_tenant_withdrawal_isolation(self):
        """Payouts and balances are completely isolated between organizations"""
        # Org 1 generates ₦100,000 revenue
        OnlineOrder.objects.create(
            organization=self.org1,
            branch=self.branch1,
            buyer_name='Org 1 Buyer',
            buyer_email='buyer1@test.com',
            total_amount=Decimal('100000.00'),
            payment_status='paid',
            status='confirmed'
        )
        # Bank setup for Org 2
        StoreBankAccount.objects.create(
            organization=self.org2,
            bank_name='GTBank',
            account_number='0987654321',
            account_name='Org Two Account'
        )

        # User 2 attempts to request payout for Org 2 -> should have ₦0 available balance
        balances2 = calculate_organization_balances(self.org2)
        self.assertEqual(balances2['available_balance'], Decimal('0.00'))

        success, msg, _ = request_organization_payout(self.org2, self.user2, Decimal('5000.00'))
        self.assertFalse(success)
        self.assertIn("exceeds your available balance", msg)

    def test_withdrawal_input_validation_security(self):
        """Rejects negative, 0, or below-minimum withdrawal amounts"""
        StoreBankAccount.objects.create(
            organization=self.org1,
            bank_name='First Bank',
            account_number='1122334455',
            account_name='Org One Payouts'
        )
        OnlineOrder.objects.create(
            organization=self.org1,
            branch=self.branch1,
            buyer_name='Org 1 Buyer',
            buyer_email='buyer1@test.com',
            total_amount=Decimal('100000.00'),
            payment_status='paid',
            status='confirmed'
        )

        # Test negative amount
        success, msg, _ = request_organization_payout(self.org1, self.user1, Decimal('-5000.00'))
        self.assertFalse(success)

        # Test zero amount
        success, msg, _ = request_organization_payout(self.org1, self.user1, Decimal('0.00'))
        self.assertFalse(success)

        # Test below minimum amount (₦100 < ₦500 min)
        success, msg, _ = request_organization_payout(self.org1, self.user1, Decimal('100.00'))
        self.assertFalse(success)
        self.assertIn("Minimum withdrawal amount", msg)

    def test_unauthenticated_vendor_access_denied(self):
        """Unauthenticated requests to vendor dashboard views are redirected to login"""
        payouts_url = reverse('vendor_payouts')
        orders_url = reverse('vendor_order_list')
        discounts_url = reverse('vendor_discounts')

        for url in [payouts_url, orders_url, discounts_url]:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 302)
            self.assertIn('/login', res.url)

    def test_three_pictures_support_and_fallback(self):
        """Verifies 3 image fields on Product & ProductListing, fallback cascade, and get_images property"""
        from django.core.files.uploadedfile import SimpleUploadedFile
        import io
        from PIL import Image

        # Create 3 dummy image files
        def make_test_img(color):
            buf = io.BytesIO()
            img = Image.new('RGB', (100, 100), color=color)
            img.save(buf, format='JPEG')
            buf.seek(0)
            return SimpleUploadedFile(f'{color}.jpg', buf.read(), content_type='image/jpeg')

        img1 = make_test_img('red')
        img2 = make_test_img('green')
        img3 = make_test_img('blue')

        product = Product.objects.create(
            organization=self.org1,
            branch=self.branch1,
            product_name='Tri-Photo Product',
            category=Category.objects.create(organization=self.org1, branch=self.branch1, category_name='Photo Category'),
            product_code='TRI-001',
            image=img1,
            image_detail=img2,
            image_extra=img3
        )

        inv = Inventory.objects.create(
            organization=self.org1,
            branch=self.branch1,
            product=product,
            quantity=10,
            quantity_available=10,
            sale_price=Decimal('5000.00'),
            cost_price=Decimal('3000.00')
        )

        store, _ = StoreListing.objects.get_or_create(
            organization=self.org1,
            defaults={'branch': self.branch1, 'is_active': True}
        )

        listing, _ = ProductListing.objects.get_or_create(
            store=store,
            inventory=inv,
            defaults={'is_visible': True}
        )

        # 1. Inherits all 3 images from underlying Product
        images = listing.get_images
        self.assertEqual(len(images), 3)
        self.assertEqual(listing.get_image_url, product.image.url)
        self.assertEqual(listing.get_image_detail_url, product.image_detail.url)
        self.assertEqual(listing.get_image_extra_url, product.image_extra.url)

        # 2. Overriding listing images
        listing_img3 = make_test_img('yellow')
        listing.image_extra = listing_img3
        listing.save()

        self.assertNotEqual(listing.get_image_extra_url, product.image_extra.url)
        self.assertEqual(len(listing.get_images), 3)

    def test_merchant_order_notification_email_owner_and_online_store_email(self):
        """Test sending order notification to owner and secondary online_store_email with deduplication"""
        from django.core import mail
        from store.emails import send_merchant_order_notification_email

        mail.outbox = []
        store, _ = StoreListing.objects.get_or_create(
            organization=self.org1,
            defaults={'branch': self.branch1, 'is_active': True}
        )
        store.online_store_email = 'manager@teststore.com'
        store.save()

        order = OnlineOrder.objects.create(
            organization=self.org1,
            branch=self.branch1,
            order_number='ORD-MERCH-001',
            buyer_name='Alice Buyer',
            buyer_email='alice@example.com',
            buyer_phone='08011112222',
            shipping_address='45 Victoria Island, Lagos',
            subtotal=Decimal('10000.00'),
            total_amount=Decimal('10000.00'),
            payment_status='paid',
            status='confirmed'
        )
        OnlineOrderItem.objects.create(
            order=order,
            product_name='Designer Handbag',
            unit_price=Decimal('10000.00'),
            quantity=1,
            total_price=Decimal('10000.00')
        )

        # 1. Send notification with distinct online_store_email
        result = send_merchant_order_notification_email(order.id)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertIn(self.user1.email, sent_email.to)
        self.assertIn('manager@teststore.com', sent_email.to)
        self.assertEqual(len(sent_email.to), 2)
        self.assertIn('ORD-MERCH-001', sent_email.subject)

        # 2. Test Deduplication: when online_store_email equals owner email (case-insensitive)
        mail.outbox = []
        store.online_store_email = f" {self.user1.email.upper()} "
        store.save()

        result = send_merchant_order_notification_email(order.id)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(len(sent_email.to), 1)
        self.assertEqual(sent_email.to[0], self.user1.email)

    def test_store_settings_post_updates_online_store_email(self):
        """Test updating online_store_email via vendor store settings POST"""
        self.client.force_login(self.user1)
        response = self.client.post(reverse('store_settings'), {
            'is_active': 'on',
            'branch_id': str(self.branch1.id),
            'tagline': 'Modern Elegance',
            'announcement': 'Special discount today',
            'contact_email': 'support@teststore.com',
            'online_store_email': 'notifications@teststore.com',
            'contact_phone': '08099998888',
            'instagram_handle': 'teststore_ng',
            'whatsapp_number': '2348099998888',
            'primary_color': '#2563eb',
        })
        self.assertRedirects(response, reverse('store_settings'))

        store = StoreListing.objects.get(organization=self.org1)
        self.assertEqual(store.online_store_email, 'notifications@teststore.com')
        self.assertEqual(store.contact_email, 'support@teststore.com')


