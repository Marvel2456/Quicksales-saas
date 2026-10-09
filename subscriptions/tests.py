from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from account.models import CustomUser, Organization
from subscriptions.models import Payment, Plan, Subscription
from subscriptions.views import _finalize_successful_payment


class PaymentIdempotencyTests(TestCase):
	def setUp(self):
		Plan.objects.all().delete()
		self.owner = CustomUser.objects.create_user(
			email="owner@example.com",
			password="testpass123",
		)
		self.organization = Organization.objects.create(
			name="Acme Retail",
			owned_by=self.owner,
		)
		self.plan = Plan.objects.create(
			name="Growth Starter Monthly",
			tier="growth",
			size="starter",
			billing_frequency="monthly",
			price=Decimal("35000.00"),
			duration_in_days=30,
			max_users=5,
			max_branches=5,
			max_products=1000,
		)
		self.subscription = Subscription.objects.create(
			organization=self.organization,
			plan=self.plan,
			provider="squadco",
			currency="NGN",
			start_date=timezone.now(),
			end_date=timezone.now() + timedelta(days=30),
			is_active=False,
		)
		self.payment = Payment.objects.create(
			subscription=self.subscription,
			amount=Decimal("35000.00"),
			payment_method="squadco",
			transaction_id="txn-idempotent-001",
			payment_status="pending",
		)

	@patch("subscriptions.views.task_send_subscription_success_email.delay")
	@patch("subscriptions.views.deactivate_subscription.apply_async")
	def test_finalize_payment_is_idempotent(self, mock_apply_async, mock_send_email):
		first_status, _ = _finalize_successful_payment(self.payment.transaction_id)
		second_status, _ = _finalize_successful_payment(self.payment.transaction_id)

		self.payment.refresh_from_db()
		self.subscription.refresh_from_db()

		self.assertEqual(first_status, "completed_now")
		self.assertEqual(second_status, "already_completed")
		self.assertEqual(self.payment.payment_status, "completed")
		self.assertTrue(self.subscription.is_active)

		mock_apply_async.assert_called_once()
		mock_send_email.assert_called_once()

	def test_finalize_payment_not_found(self):
		status, payment = _finalize_successful_payment("missing-reference")

		self.assertEqual(status, "not_found")
		self.assertIsNone(payment)

	@patch("subscriptions.views.task_send_subscription_success_email.delay")
	@patch("subscriptions.views.deactivate_subscription.apply_async")
	@patch("subscriptions.views.requests.get")
	def test_verify_payment_success_callback_completes_pending_payment(
		self,
		mock_requests_get,
		mock_apply_async,
		mock_send_email,
	):
		mock_response = Mock()
		mock_response.status_code = 200
		mock_response.json.return_value = {
			"status": 200,
			"data": {
				"transaction_status": "success",
			}
		}
		mock_requests_get.return_value = mock_response

		response = self.client.get(reverse("verify_payment"), {
			"reference": self.payment.transaction_id,
		})

		self.payment.refresh_from_db()
		self.subscription.refresh_from_db()

		self.assertEqual(response.status_code, 302)
		self.assertEqual(self.payment.payment_status, "completed")
		self.assertTrue(self.subscription.is_active)
		mock_apply_async.assert_called_once()
		mock_send_email.assert_called_once()


class PlanOnlineStoreFeatureTests(TestCase):
	def setUp(self):
		self.owner = CustomUser.objects.create_user(
			email="planowner@test.com",
			password="Password123!",
			role="owner"
		)
		self.organization = Organization.objects.create(
			name="Boutique One",
			slug="boutique-one",
			owned_by=self.owner,
			is_active=True
		)
		from account.models import Branch, OrganizationMembership
		self.branch = Branch.objects.create(
			name="Main Branch",
			organization=self.organization
		)
		self.organization.default_branch = self.branch
		self.organization.save()
		OrganizationMembership.objects.create(
			user=self.owner,
			organization=self.organization,
			branch=self.branch,
			role="owner",
			is_active=True
		)

		# Plan WITH online store enabled
		self.plan_with_store, _ = Plan.objects.get_or_create(
			tier="growth",
			size="starter",
			billing_frequency="monthly",
			defaults={
				"name": "Growth Plan With Store",
				"price": Decimal("25000.00"),
				"duration_in_days": 30,
				"has_online_store": True
			}
		)
		self.plan_with_store.has_online_store = True
		self.plan_with_store.save(update_fields=['has_online_store'])

		# Plan WITHOUT online store enabled
		self.plan_without_store, _ = Plan.objects.get_or_create(
			tier="basic",
			size="starter",
			billing_frequency="monthly",
			defaults={
				"name": "Basic Plan POS Only",
				"price": Decimal("10000.00"),
				"duration_in_days": 30,
				"has_online_store": False
			}
		)
		self.plan_without_store.has_online_store = False
		self.plan_without_store.save(update_fields=['has_online_store'])

	def test_plan_has_online_store_access_helper(self):
		"""Verifies has_online_store_access returns True/False according to active plan"""
		from subscriptions.utils import has_online_store_access

		sub = Subscription.objects.create(
			organization=self.organization,
			plan=self.plan_with_store,
			start_date=timezone.now(),
			end_date=timezone.now() + timedelta(days=30),
			is_active=True
		)
		self.assertTrue(has_online_store_access(self.organization))

		# Switch to plan without online store
		sub.plan = self.plan_without_store
		sub.save()
		self.assertFalse(has_online_store_access(self.organization))

	def test_vendor_store_view_restricted_when_plan_disables_store(self):
		"""Vendor views redirect to pricing with warning when plan does not include online store"""
		Subscription.objects.create(
			organization=self.organization,
			plan=self.plan_without_store,
			start_date=timezone.now(),
			end_date=timezone.now() + timedelta(days=30),
			is_active=True
		)

		self.client.force_login(self.owner)
		url = reverse('manage_listings')
		res = self.client.get(url)
		# Redirects to subscription settings
		self.assertEqual(res.status_code, 302)
		self.assertIn('/settings', res.url)

	def test_public_storefront_inactive_when_plan_disables_store(self):
		"""Public storefront renders inactive template when owner's plan does not have online store"""
		Subscription.objects.create(
			organization=self.organization,
			plan=self.plan_without_store,
			start_date=timezone.now(),
			end_date=timezone.now() + timedelta(days=30),
			is_active=True
		)

		url = reverse('storefront', kwargs={'org_slug': self.organization.slug})
		res = self.client.get(url)
		self.assertEqual(res.status_code, 200)
		self.assertTemplateUsed(res, 'store/store_inactive.html')

