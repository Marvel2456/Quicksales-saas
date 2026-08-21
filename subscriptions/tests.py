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
