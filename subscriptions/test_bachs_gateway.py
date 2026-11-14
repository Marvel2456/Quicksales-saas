import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from account.models import Branch, Organization
from ims.models import Category, Inventory, Product
from store.admin import StorePayoutAdmin
from store.models import (
    OnlineOrder,
    OnlineOrderItem,
    ProductListing,
    StoreBankAccount,
    StoreListing,
    StorePayout,
)
from store.vendor_views import request_organization_payout
from subscriptions.models import Payment, PaymentGatewayConfig, Plan, Subscription, WebhookEvent
from subscriptions.services.gateways import (
    BachsGateway,
    SquadGateway,
    get_active_gateway_name,
    get_gateway_client,
    validate_positive_amount,
    verify_amount_and_currency,
)

User = get_user_model()


def _sign_bachs_payload(raw_body: bytes, secret: str, ts: int | None = None) -> str:
    ts = ts if ts is not None else int(time.time())
    signed = f"{ts}.{raw_body.decode('utf-8')}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


@override_settings(
    BACHS_API_KEY="sk_sandbox_test_key",
    BACHS_WEBHOOK_SECRET="whsec_test_secret_123",
    BACHS_API_BASE_URL="https://sandbox-api.bachs.io",
)
class BachsGatewaySecurityAndSwitchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com",
            password="password123",
            first_name="Ada",
            last_name="Obi",
        )
        self.superuser = User.objects.create_superuser(
            email="admin@example.com",
            password="password123",
        )
        self.org = Organization.objects.create(
            name="Test Org",
            slug="test-org",
            owned_by=self.user,
            country="Nigeria",
            is_active=True,
        )
        self.branch = Branch.objects.create(
            organization=self.org,
            name="Main Branch",
        )
        self.plan, _ = Plan.objects.get_or_create(
            tier="basic",
            size="starter",
            billing_frequency="monthly",
            defaults={
                "name": "Basic Monthly",
                "price": Decimal("5000.00"),
                "price_usd": Decimal("5.00"),
                "duration_in_days": 30,
            },
        )
        self.store = StoreListing.objects.create(
            organization=self.org,
            branch=self.branch,
            is_active=True,
        )
        self.bank_account = StoreBankAccount.objects.create(
            organization=self.org,
            bank_name="GTBank",
            bank_code="058",
            account_number="0123456789",
            account_name="Ada Obi",
        )
        self.category = Category.objects.create(organization=self.org, category_name="Gadgets")
        self.product = Product.objects.create(
            organization=self.org,
            product_name="USB-C Hub",
            category=self.category,
        )
        self.inventory = Inventory.objects.create(
            organization=self.org,
            branch=self.branch,
            product=self.product,
            quantity=10,
            quantity_available=10,
            cost_price=Decimal("1000.00"),
            sale_price=Decimal("2500.00"),
        )
        self.listing, _ = ProductListing.objects.get_or_create(
            store=self.store,
            inventory=self.inventory,
            defaults={"is_visible": True},
        )

    def test_negative_zero_and_non_finite_amounts_rejected(self):
        for bad in ("-1000", "-0.01", "0", "0.00", "NaN", "Infinity", "-Infinity", None, True):
            with self.assertRaises(ValueError):
                validate_positive_amount(bad)

        ok, msg, payout = request_organization_payout(self.org, self.user, Decimal("-1000.00"))
        self.assertFalse(ok)
        self.assertIsNone(payout)
        self.assertEqual(StorePayout.objects.count(), 0)

        with self.assertRaises(IntegrityError):
            StorePayout.objects.create(
                organization=self.org,
                amount=Decimal("-1000.00"),
                currency="NGN",
                bank_name="GTBank",
                account_number="0123456789",
                account_name="Ada Obi",
            )

        with self.assertRaises(ValueError):
            BachsGateway().create_checkout(
                amount=Decimal("-50.00"),
                currency="NGN",
                customer_email="buyer@example.com",
                customer_name="Buyer",
                reference="ref-neg",
            )

    def test_admin_gateway_switch_defaults_to_bachs_and_toggles_squadco(self):
        self.assertEqual(get_active_gateway_name(), "bachs")
        self.assertIsInstance(get_gateway_client(), BachsGateway)

        cfg = PaymentGatewayConfig.objects.get(pk=1)
        cfg.active_gateway = "squadco"
        cfg.save()

        self.assertEqual(get_active_gateway_name(), "squadco")
        self.assertIsInstance(get_gateway_client(), SquadGateway)

    @patch("subscriptions.services.gateways.requests.post")
    def test_bachs_checkout_uses_decimal_string_and_idempotency_key(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "checkout_id": "chk_abc123",
            "checkout_url": "https://sandbox-checkout.bachs.io/c/chk_abc123",
        }
        mock_post.return_value = mock_resp

        res = BachsGateway().create_checkout(
            amount=Decimal("2500.00"),
            currency="NGN",
            customer_email="buyer@example.com",
            customer_name="Buyer",
            reference="QS-ORD-123",
            metadata={"flow_type": "store_order", "order_number": "QS-001"},
            success_url="https://example.com/callback",
        )
        self.assertEqual(res["checkout_id"], "chk_abc123")
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["Idempotency-Key"], "chk-QS-ORD-123")
        self.assertEqual(kwargs["json"]["pricing"], {"amount": "2500.00", "currency": "NGN"})

    def test_amount_and_currency_tamper_checks(self):
        ok, _ = verify_amount_and_currency(Decimal("2500.00"), "NGN", Decimal("2500.00"), "NGN")
        self.assertTrue(ok)

        ok_under, _ = verify_amount_and_currency(Decimal("2500.00"), "NGN", Decimal("100.00"), "NGN")
        self.assertFalse(ok_under)

        ok_curr, _ = verify_amount_and_currency(Decimal("2500.00"), "USD", Decimal("2500.00"), "NGN")
        self.assertFalse(ok_curr)

    def test_webhook_signature_and_replay_protection(self):
        gw = BachsGateway()
        body = b'{"id":"evt_1","type":"checkout.completed"}'
        valid_sig = _sign_bachs_payload(body, "whsec_test_secret_123")

        self.assertTrue(gw.verify_webhook_signature(body, valid_sig)[0])
        self.assertFalse(gw.verify_webhook_signature(b'{"id":"evt_tampered"}', valid_sig)[0])
        self.assertFalse(gw.verify_webhook_signature(body, _sign_bachs_payload(body, "wrong"))[0])

        expired_sig = _sign_bachs_payload(body, "whsec_test_secret_123", ts=int(time.time()) - 600)
        self.assertFalse(gw.verify_webhook_signature(body, expired_sig)[0])

    @override_settings(DEBUG=True)
    @patch("subscriptions.services.gateways.requests.get")
    def test_store_callback_never_bypasses_verification_in_debug(self, mock_get):
        order = OnlineOrder.objects.create(
            organization=self.org,
            branch=self.branch,
            buyer_name="Buyer",
            buyer_email="buyer@example.com",
            payment_method="bachs",
            payment_status="pending",
            payment_reference="QS-ORD-DBG1",
            gateway_checkout_id="chk_unpaid",
            currency="NGN",
            subtotal=Decimal("2500.00"),
            total_amount=Decimal("2500.00"),
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "checkout_id": "chk_unpaid",
            "status": "pending",
            "amount": "2500.00",
            "currency": "NGN",
        }
        mock_get.return_value = mock_resp

        client = Client()
        url = reverse("store_payment_callback", kwargs={"org_slug": self.org.slug})
        resp = client.get(f"{url}?reference=QS-ORD-DBG1")
        self.assertEqual(resp.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "failed")

    @patch("store.views.complete_order_sale")
    def test_bachs_webhook_is_idempotent_and_deduplicates_events(self, mock_complete):
        order = OnlineOrder.objects.create(
            organization=self.org,
            branch=self.branch,
            buyer_name="Buyer",
            buyer_email="buyer@example.com",
            payment_method="bachs",
            payment_status="pending",
            payment_reference="QS-ORD-WH1",
            gateway_checkout_id="chk_wh_1",
            currency="NGN",
            subtotal=Decimal("2500.00"),
            total_amount=Decimal("2500.00"),
        )
        OnlineOrderItem.objects.create(
            order=order,
            product_listing=self.listing,
            inventory=self.inventory,
            product_name="USB-C Hub",
            unit_price=Decimal("2500.00"),
            quantity=1,
            total_price=Decimal("2500.00"),
        )

        payload_dict = {
            "id": "evt_unique_001",
            "type": "checkout.completed",
            "data": {
                "checkout_id": "chk_wh_1",
                "amount": "2500.00",
                "currency": "NGN",
                "metadata": {
                    "flow_type": "store_order",
                    "order_number": order.order_number,
                },
            },
        }
        raw_body = json.dumps(payload_dict).encode("utf-8")
        sig = _sign_bachs_payload(raw_body, "whsec_test_secret_123")

        client = Client()
        url = reverse("bachs_webhook")
        r1 = client.post(url, data=raw_body, content_type="application/json", HTTP_X_BACHS_SIGNATURE_V2=sig)
        r2 = client.post(url, data=raw_body, content_type="application/json", HTTP_X_BACHS_SIGNATURE_V2=sig)

        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(WebhookEvent.objects.filter(provider="bachs", event_id="evt_unique_001").count(), 1)
        self.assertEqual(mock_complete.call_count, 1)

    @patch("subscriptions.services.gateways.requests.post")
    def test_admin_payout_disbursement_via_bachs_and_snapshot_guard(self, mock_post):
        def _side_effect(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 201
            if url.endswith("/v1/payouts/destinations"):
                resp.json.return_value = {"id": "pd_dest_123", "is_usable": True}
            else:
                resp.json.return_value = {"id": "po_bachs_999", "status": "processing"}
            return resp

        mock_post.side_effect = _side_effect

        payout = StorePayout.objects.create(
            organization=self.org,
            amount=Decimal("2000.00"),
            currency="NGN",
            bank_name="GTBank",
            account_number="0123456789",
            account_name="Ada Obi",
            status="pending",
            idempotency_key="idem-payout-001",
        )

        admin_instance = StorePayoutAdmin(StorePayout, AdminSite())
        req = RequestFactory().post("/admin/store/storepayout/")
        req.user = self.superuser
        # Attach messages storage stub
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(req, "session", "session")
        setattr(req, "_messages", FallbackStorage(req))

        admin_instance.approve_and_disburse_via_gateway(req, StorePayout.objects.filter(id=payout.id))

        payout.refresh_from_db()
        self.bank_account.refresh_from_db()
        self.assertEqual(payout.status, "processing")
        self.assertEqual(payout.gateway, "bachs")
        self.assertEqual(payout.gateway_reference, "po_bachs_999")
        self.assertEqual(self.bank_account.bachs_destination_id, "pd_dest_123")

    def test_root_webhook_url_and_plain_bachs_signature_header(self):
        body = json.dumps({
            "id": "evt_root_001",
            "type": "payout.paid",
            "data": {"reference": "WD-TEST-999"},
        }).encode("utf-8")
        payout = StorePayout.objects.create(
            organization=self.org,
            reference="WD-TEST-999",
            amount=Decimal("1000.00"),
            currency="NGN",
            bank_name="GTBank",
            account_number="0123456789",
            account_name="Ada Obi",
            status="processing",
        )
        raw_sig = hmac.new(b"whsec_test_secret_123", body, hashlib.sha256).hexdigest()

        client = Client()
        resp = client.post(
            reverse("bachs_webhook_root"),
            data=body,
            content_type="application/json",
            HTTP_BACHS_SIGNATURE=raw_sig,
        )
        self.assertEqual(resp.status_code, 200)
        payout.refresh_from_db()
        self.assertEqual(payout.status, "completed")
        self.assertIsNotNone(payout.processed_at)

    def test_platform_settlement_summary_separates_ours_from_customer_funds(self):
        from django.utils import timezone
        from subscriptions.services.settlement import get_platform_settlement_summary

        sub = Subscription.objects.create(
            organization=self.org,
            plan=self.plan,
            provider="bachs",
            currency="NGN",
            end_date=timezone.now() + timezone.timedelta(days=30),
            is_active=True,
        )
        Payment.objects.create(
            subscription=sub,
            amount=Decimal("15000.00"),
            currency="NGN",
            payment_method="bachs",
            transaction_id="sub-pay-001",
            payment_status="completed",
        )
        OnlineOrder.objects.create(
            organization=self.org,
            branch=self.branch,
            buyer_name="Buyer",
            buyer_email="buyer@example.com",
            payment_method="bachs",
            payment_status="paid",
            payment_reference="ORD-SET-1",
            currency="NGN",
            subtotal=Decimal("8000.00"),
            total_amount=Decimal("8000.00"),
        )
        StorePayout.objects.create(
            organization=self.org,
            amount=Decimal("3000.00"),
            currency="NGN",
            bank_name="GTBank",
            account_number="0123456789",
            account_name="Ada Obi",
            status="completed",
        )

        ngn = get_platform_settlement_summary()["by_currency"]["NGN"]
        self.assertEqual(ngn["safe_to_settle_ours"], Decimal("15000.00"))
        self.assertEqual(ngn["customer_gross"], Decimal("8000.00"))
        self.assertEqual(ngn["customer_paid_out"], Decimal("3000.00"))
        self.assertEqual(ngn["customer_withdrawable_held"], Decimal("5000.00"))
        self.assertEqual(ngn["expected_gateway_balance"], Decimal("20000.00"))

    def test_ngrok_host_allowed_by_subdomain_middleware_in_debug(self):
        from django.test import override_settings
        from ImsV3.middleware import SubdomainOrganizationMiddleware

        middleware = SubdomainOrganizationMiddleware(lambda req: None)

        with override_settings(DEBUG=True):
            req = RequestFactory().get(
                "/subscriptions/plan/verify/?reference=abc",
                HTTP_HOST="lise-strained-beula.ngrok-free.dev",
            )
            res = middleware.process_request(req)
            self.assertIsNone(res)
            self.assertIsNone(req.organization)

        with override_settings(DEBUG=False):
            req = RequestFactory().get(
                "/subscriptions/plan/verify/?reference=abc",
                HTTP_HOST="unknown-org.marvexqs.com",
            )
            res = middleware.process_request(req)
            self.assertIsNotNone(res)
            self.assertEqual(res.status_code, 404)
            self.assertEqual(res.content, b"Organization not found")

    @patch("subscriptions.services.gateways.requests.post")
    def test_automatic_withdrawal_with_admin_min_and_settled_balance_only(self, mock_post):
        from store.vendor_views import request_organization_payout, calculate_organization_balances

        def _side_effect(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 201
            if url.endswith("/v1/payouts/destinations"):
                resp.json.return_value = {"id": "pd_auto_123", "is_usable": True}
            else:
                resp.json.return_value = {"id": "po_auto_999", "status": "processing"}
            return resp

        mock_post.side_effect = _side_effect

        # Paid online order -> withdrawable
        OnlineOrder.objects.create(
            organization=self.org,
            branch=self.branch,
            buyer_name="Paid Buyer",
            buyer_email="paid@example.com",
            payment_method="bachs",
            payment_status="paid",
            payment_reference="ORD-PAID-AUTO",
            currency="NGN",
            subtotal=Decimal("3000.00"),
            total_amount=Decimal("3000.00"),
        )
        # Confirmed COD order -> NOT settled online, must NOT be withdrawable
        OnlineOrder.objects.create(
            organization=self.org,
            branch=self.branch,
            buyer_name="COD Buyer",
            buyer_email="cod@example.com",
            payment_method="cod",
            payment_status="pending",
            status="confirmed",
            currency="NGN",
            subtotal=Decimal("5000.00"),
            total_amount=Decimal("5000.00"),
        )

        balances = calculate_organization_balances(self.org)
        self.assertEqual(balances["available_balance"], Decimal("3000.00"))

        # Admin sets minimum withdrawal to 1500.00
        cfg, _ = PaymentGatewayConfig.objects.get_or_create(pk=1)
        cfg.minimum_withdrawal_ngn = Decimal("1500.00")
        cfg.save()

        ok_low, msg_low, _ = request_organization_payout(self.org, self.user, Decimal("1000.00"))
        self.assertFalse(ok_low)
        self.assertIn("1,500.00", msg_low)

        ok_over, msg_over, _ = request_organization_payout(self.org, self.user, Decimal("4000.00"))
        self.assertFalse(ok_over)
        self.assertIn("exceeds your available balance", msg_over)

        ok, _, payout = request_organization_payout(self.org, self.user, Decimal("2000.00"))
        self.assertTrue(ok)
        self.assertEqual(payout.status, "processing")
        self.assertEqual(payout.gateway, "bachs")
        self.assertEqual(payout.gateway_reference, "po_auto_999")
        self.assertEqual(calculate_organization_balances(self.org)["available_balance"], Decimal("1000.00"))
