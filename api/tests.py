from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from account.models import (
    Branch,
    CustomUser,
    Organization,
    OrganizationMembership,
)
from ims.models import Category, Inventory, Invoice, Product, Sale
from subscriptions.models import Plan, Subscription


class MobileApiPhase1Tests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.org = Organization.objects.create(
            name="Acme Retail",
            business_type="Retail",
            country="Nigeria",
            is_active=True,
        )
        self.branch_a = Branch.objects.create(
            organization=self.org,
            name="Branch A",
            address="100 Main St",
        )
        self.branch_b = Branch.objects.create(
            organization=self.org,
            name="Branch B",
            address="200 Side St",
        )

        self.plan, _ = Plan.objects.get_or_create(
            tier="basic",
            size="starter",
            billing_frequency="monthly",
            defaults={
                "name": "Starter Monthly",
                "price": 1000,
                "price_usd": 5,
                "duration_in_days": 30,
            },
        )
        self.subscription = Subscription.objects.create(
            organization=self.org,
            plan=self.plan,
            currency="NGN",
            start_date=timezone.now() - timedelta(days=1),
            end_date=timezone.now() + timedelta(days=29),
            is_active=True,
        )

        self.owner = CustomUser.objects.create_user(
            email="Owner@Acme.com",
            password="SecretPassword123!",
            first_name="Jane",
            last_name="Owner",
            organization=self.org,
            branch=self.branch_a,
            role="owner",
            is_active=True,
        )
        self.org.owned_by = self.owner
        self.org.save(update_fields=["owned_by"])
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            branch=self.branch_a,
            role="owner",
            is_active=True,
        )

        self.rep_no_perm = CustomUser.objects.create_user(
            email="rep1@acme.com",
            password="RepPassword123!",
            first_name="Bob",
            last_name="Rep",
            organization=self.org,
            branch=self.branch_a,
            role="sales",
            is_active=True,
        )
        OrganizationMembership.objects.create(
            user=self.rep_no_perm,
            organization=self.org,
            branch=self.branch_a,
            role="sales",
            permissions=[],
            is_active=True,
        )

        self.rep_with_inv = CustomUser.objects.create_user(
            email="rep2@acme.com",
            password="RepPassword123!",
            first_name="Alice",
            last_name="Rep",
            organization=self.org,
            branch=self.branch_a,
            role="sales",
            is_active=True,
        )
        OrganizationMembership.objects.create(
            user=self.rep_with_inv,
            organization=self.org,
            branch=self.branch_a,
            role="sales",
            permissions=["invoices"],
            is_active=True,
        )

        self.category = Category.objects.create(
            organization=self.org,
            branch=self.branch_a,
            category_name="Electronics",
        )
        self.product = Product.objects.create(
            organization=self.org,
            branch=self.branch_a,
            category=self.category,
            product_name="Wireless Mouse",
            product_code="WM-001",
            brand="Logi",
            unit="pcs",
        )
        self.inv_a = Inventory.objects.create(
            organization=self.org,
            branch=self.branch_a,
            product=self.product,
            quantity=20,
            quantity_available=20,
            reorder_level=5,
            cost_price=500.0,
            sale_price=1000.0,
        )
        self.inv_b = Inventory.objects.create(
            organization=self.org,
            branch=self.branch_b,
            product=self.product,
            quantity=15,
            quantity_available=15,
            reorder_level=5,
            cost_price=500.0,
            sale_price=1200.0,
        )

    def _login(self, email, password):
        return self.client.post(
            "/api/v1/mobile/auth/login/",
            {"email": email, "password": password},
            format="json",
        )

    def _auth_headers(self, token, org_id=None, branch_id=None):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        if org_id:
            headers["HTTP_X_ORGANIZATION_ID"] = str(org_id)
        if branch_id:
            headers["HTTP_X_BRANCH_ID"] = str(branch_id)
        return headers

    def test_login_case_insensitive_email_and_case_sensitive_password(self):
        # Wrong password case fails
        bad_pw = self._login("owner@acme.com", "secretpassword123!")
        self.assertEqual(bad_pw.status_code, 401)

        # Lowercase email with exact password succeeds
        resp = self._login("owner@acme.com", "SecretPassword123!")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertEqual(resp.data["active_role"], "owner")

        # Refresh works
        refresh_resp = self.client.post(
            "/api/v1/mobile/auth/token/refresh/",
            {"refresh": resp.data["refresh"]},
            format="json",
        )
        self.assertEqual(refresh_resp.status_code, 200)
        self.assertIn("access", refresh_resp.data)

        # Logout blacklists refresh token
        new_refresh = refresh_resp.data.get("refresh", resp.data["refresh"])
        logout_resp = self.client.post(
            "/api/v1/mobile/auth/logout/",
            {"refresh": new_refresh},
            format="json",
            **self._auth_headers(refresh_resp.data["access"]),
        )
        self.assertEqual(logout_resp.status_code, 200)

    def test_must_change_password_and_subscription_guards_return_json(self):
        self.owner.must_change_password = True
        self.owner.save(update_fields=["must_change_password"])

        login_resp = self._login("owner@acme.com", "SecretPassword123!")
        token = login_resp.data["access"]
        self.assertTrue(login_resp.data["must_change_password"])

        # Blocked with 403 JSON (no 302 HTML redirect)
        blocked = self.client.get(
            "/api/v1/mobile/dashboard/summary/",
            **self._auth_headers(token),
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.data["code"], "password_change_required")

        # Change password clears flag and returns fresh tokens
        chg = self.client.post(
            "/api/v1/mobile/auth/change-password/",
            {
                "new_password": "NewStrongPassword99!",
                "confirm_password": "NewStrongPassword99!",
            },
            format="json",
            **self._auth_headers(token),
        )
        self.assertEqual(chg.status_code, 200)
        self.assertFalse(chg.data["must_change_password"])
        fresh_token = chg.data["access"]

        # Expired subscription returns 402 JSON
        self.subscription.end_date = timezone.now() - timedelta(days=1)
        self.subscription.save(update_fields=["end_date"])
        sub_blocked = self.client.get(
            "/api/v1/mobile/dashboard/summary/",
            **self._auth_headers(fresh_token),
        )
        self.assertEqual(sub_blocked.status_code, 402)
        self.assertEqual(sub_blocked.data["code"], "subscription_expired")

    def test_branch_isolation_for_owner_vs_staff(self):
        owner_token = self._login("owner@acme.com", "SecretPassword123!").data["access"]
        rep_token = self._login("rep1@acme.com", "RepPassword123!").data["access"]

        # Owner can switch to Branch B
        owner_b = self.client.get(
            "/api/v1/mobile/pos/catalog/",
            **self._auth_headers(owner_token, self.org.id, self.branch_b.id),
        )
        self.assertEqual(owner_b.status_code, 200)
        self.assertEqual(owner_b.data[0]["sale_price"], 1200.0)

        # Rep locked to Branch A cannot access Branch B
        rep_b = self.client.get(
            "/api/v1/mobile/pos/catalog/",
            **self._auth_headers(rep_token, self.org.id, self.branch_b.id),
        )
        self.assertEqual(rep_b.status_code, 403)

    def test_pos_checkout_and_offline_sync_idempotency(self):
        rep_token = self._login("rep1@acme.com", "RepPassword123!").data["access"]
        headers = self._auth_headers(rep_token, self.org.id, self.branch_a.id)

        # Direct checkout of 2 units
        checkout = self.client.post(
            "/api/v1/mobile/pos/checkout/",
            {
                "method": "Cash",
                "discount": 100,
                "items": [{"inventory_id": str(self.inv_a.id), "quantity": 2}],
            },
            format="json",
            **headers,
        )
        self.assertEqual(checkout.status_code, 200)
        self.assertEqual(checkout.data["final_total_price"], 1900.0)
        self.inv_a.refresh_from_db()
        self.assertEqual(self.inv_a.quantity, 18)

        # Offline sync with tempId
        sync_payload = {
            "tempId": "OFFLINE-MOBILE-001",
            "method": "Transfer",
            "items": [{"inventory_id": str(self.inv_a.id), "quantity": 3}],
        }
        sync_1 = self.client.post(
            "/api/v1/mobile/pos/sync-offline/",
            sync_payload,
            format="json",
            **headers,
        )
        self.assertEqual(sync_1.status_code, 201)
        self.assertFalse(sync_1.data["idempotent"])
        self.inv_a.refresh_from_db()
        self.assertEqual(self.inv_a.quantity, 15)

        # Retry same tempId -> idempotent, no second deduction
        sync_2 = self.client.post(
            "/api/v1/mobile/pos/sync-offline/",
            sync_payload,
            format="json",
            **headers,
        )
        self.assertEqual(sync_2.status_code, 200)
        self.assertTrue(sync_2.data["idempotent"])
        self.assertEqual(sync_2.data["sale"]["id"], sync_1.data["sale"]["id"])
        self.inv_a.refresh_from_db()
        self.assertEqual(self.inv_a.quantity, 15)

    def test_invoice_permissions_ownership_and_installments(self):
        no_perm_token = self._login("rep1@acme.com", "RepPassword123!").data["access"]
        rep_token = self._login("rep2@acme.com", "RepPassword123!").data["access"]
        owner_token = self._login("owner@acme.com", "SecretPassword123!").data["access"]

        # Rep without invoices permission gets 403
        denied = self.client.get(
            "/api/v1/mobile/invoices/",
            **self._auth_headers(no_perm_token, self.org.id, self.branch_a.id),
        )
        self.assertEqual(denied.status_code, 403)

        # Owner creates an invoice in Branch A
        owner_inv = self.client.post(
            "/api/v1/mobile/invoices/",
            {
                "customer_name": "Owner Client",
                "payment_plan": "one_time",
                "items": [{"inventory_id": str(self.inv_a.id), "quantity": 2}],
            },
            format="json",
            **self._auth_headers(owner_token, self.org.id, self.branch_a.id),
        )
        self.assertEqual(owner_inv.status_code, 201)
        owner_inv_id = owner_inv.data["id"]

        # Rep2 with permission creates her own invoice
        rep_inv = self.client.post(
            "/api/v1/mobile/invoices/",
            {
                "customer_name": "Rep Client",
                "payment_plan": "installment",
                "items": [{"inventory_id": str(self.inv_a.id), "quantity": 4}],
            },
            format="json",
            **self._auth_headers(rep_token, self.org.id, self.branch_a.id),
        )
        self.assertEqual(rep_inv.status_code, 201)
        rep_inv_id = rep_inv.data["id"]
        self.assertEqual(rep_inv.data["total_amount"], 4000.0)

        # Rep2 only sees her own invoice, NOT owner's invoice
        rep_list = self.client.get(
            "/api/v1/mobile/invoices/",
            **self._auth_headers(rep_token, self.org.id, self.branch_a.id),
        )
        self.assertEqual(rep_list.status_code, 200)
        self.assertEqual(rep_list.data["count"], 1)
        self.assertEqual(len(rep_list.data["results"]), 1)
        self.assertEqual(rep_list.data["results"][0]["id"], rep_inv_id)

        # Rep2 cannot access owner's invoice detail
        rep_forbidden_detail = self.client.get(
            f"/api/v1/mobile/invoices/{owner_inv_id}/",
            **self._auth_headers(rep_token, self.org.id, self.branch_a.id),
        )
        self.assertEqual(rep_forbidden_detail.status_code, 404)

        # Owner sees both invoices
        owner_list = self.client.get(
            "/api/v1/mobile/invoices/",
            **self._auth_headers(owner_token, self.org.id, self.branch_a.id),
        )
        self.assertEqual(owner_list.status_code, 200)
        self.assertEqual(owner_list.data["count"], 2)
        self.assertEqual(len(owner_list.data["results"]), 2)

        # Rep2 records partial payment (1500 of 4000) -> inventory deducted once, status partially_paid
        pay1 = self.client.post(
            f"/api/v1/mobile/invoices/{rep_inv_id}/record-payment/",
            {"amount": 1500, "payment_method": "Cash", "notes": "First deposit"},
            format="json",
            **self._auth_headers(rep_token, self.org.id, self.branch_a.id),
        )
        self.assertEqual(pay1.status_code, 200)
        self.assertEqual(pay1.data["status"], "partially_paid")
        self.assertEqual(pay1.data["balance_due"], 2500.0)
        self.inv_a.refresh_from_db()
        self.assertEqual(self.inv_a.quantity, 16)

        # Owner records remaining balance (2500) -> status paid, Sale created, inventory NOT deducted again
        pay2 = self.client.post(
            f"/api/v1/mobile/invoices/{rep_inv_id}/record-payment/",
            {"amount": 2500, "payment_method": "Transfer"},
            format="json",
            **self._auth_headers(owner_token, self.org.id, self.branch_a.id),
        )
        self.assertEqual(pay2.status_code, 200)
        self.assertEqual(pay2.data["status"], "paid")
        self.assertEqual(pay2.data["balance_due"], 0.0)
        self.inv_a.refresh_from_db()
        self.assertEqual(self.inv_a.quantity, 16)
        self.assertTrue(Sale.objects.filter(organization=self.org, final_total_price=4000.0, completed=True).exists())

        # Owner closes and reopens their pending invoice; rep cannot reopen
        close_resp = self.client.post(
            f"/api/v1/mobile/invoices/{owner_inv_id}/close/",
            {},
            format="json",
            **self._auth_headers(owner_token, self.org.id, self.branch_a.id),
        )
        self.assertEqual(close_resp.status_code, 200)
        self.assertEqual(close_resp.data["status"], "closed")

        reopen_rep = self.client.post(
            f"/api/v1/mobile/invoices/{owner_inv_id}/reopen/",
            {},
            format="json",
            **self._auth_headers(rep_token, self.org.id, self.branch_a.id),
        )
        self.assertEqual(reopen_rep.status_code, 403)

        reopen_owner = self.client.post(
            f"/api/v1/mobile/invoices/{owner_inv_id}/reopen/",
            {},
            format="json",
            **self._auth_headers(owner_token, self.org.id, self.branch_a.id),
        )
        self.assertEqual(reopen_owner.status_code, 200)
        self.assertEqual(reopen_owner.data["status"], "pending")

        # PDF export returns 200 application/pdf
        pdf_resp = self.client.get(
            f"/api/v1/mobile/invoices/{rep_inv_id}/pdf/",
            **self._auth_headers(rep_token, self.org.id, self.branch_a.id),
        )
        self.assertEqual(pdf_resp.status_code, 200)
        self.assertEqual(pdf_resp["Content-Type"], "application/pdf")


class MobileApiPhase2Tests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(
            name="Phase2 Corp",
            business_type="Retail",
            country="Nigeria",
            is_active=True,
        )
        self.branch_a = Branch.objects.create(
            organization=self.org,
            name="Branch A",
            address="100 Main St",
        )
        self.branch_b = Branch.objects.create(
            organization=self.org,
            name="Branch B",
            address="200 Side St",
        )
        self.plan, _ = Plan.objects.get_or_create(
            tier="basic",
            size="starter",
            billing_frequency="monthly",
            defaults={
                "name": "Starter Monthly",
                "price": 1000,
                "price_usd": 5,
                "duration_in_days": 30,
            },
        )
        Subscription.objects.create(
            organization=self.org,
            plan=self.plan,
            currency="NGN",
            start_date=timezone.now() - timedelta(days=1),
            end_date=timezone.now() + timedelta(days=29),
            is_active=True,
        )
        self.owner = CustomUser.objects.create_user(
            email="owner2@phase2.com",
            password="OwnerPassword123!",
            first_name="Sam",
            last_name="Owner",
            organization=self.org,
            branch=self.branch_a,
            role="owner",
            is_active=True,
        )
        self.org.owned_by = self.owner
        self.org.save(update_fields=["owned_by"])
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            branch=self.branch_a,
            role="owner",
            is_active=True,
        )

    def _login_headers(self, email, password, branch_id=None):
        resp = self.client.post(
            "/api/v1/mobile/auth/login/",
            {"email": email, "password": password},
            format="json",
        )
        token = resp.data["access"]
        headers = {
            "HTTP_AUTHORIZATION": f"Bearer {token}",
            "HTTP_X_ORGANIZATION_ID": str(self.org.id),
        }
        if branch_id:
            headers["HTTP_X_BRANCH_ID"] = str(branch_id)
        return headers

    def test_categories_products_inventory_restock_and_count(self):
        headers = self._login_headers("owner2@phase2.com", "OwnerPassword123!", self.branch_a.id)

        cat = self.client.post(
            "/api/v1/mobile/categories/",
            {"category_name": "Accessories"},
            format="json",
            **headers,
        )
        self.assertEqual(cat.status_code, 201)
        cat_id = cat.data["id"]

        prod = self.client.post(
            "/api/v1/mobile/products/",
            {
                "product_name": "USB-C Hub",
                "category": cat_id,
                "product_code": "HUB-01",
                "brand": "Anker",
                "unit": "pcs",
            },
            format="json",
            **headers,
        )
        self.assertEqual(prod.status_code, 201)
        prod_id = prod.data["id"]

        inv = self.client.post(
            "/api/v1/mobile/inventory/",
            {
                "product": prod_id,
                "quantity": 10,
                "cost_price": 4000,
                "sale_price": 6500,
                "reorder_level": 3,
            },
            format="json",
            **headers,
        )
        self.assertEqual(inv.status_code, 201)
        inv_id = inv.data["id"]

        restock = self.client.post(
            f"/api/v1/mobile/inventory/{inv_id}/restock/",
            {"quantity_added": 5, "sale_price": 7000},
            format="json",
            **headers,
        )
        self.assertEqual(restock.status_code, 200)
        self.assertEqual(restock.data["quantity"], 15)
        self.assertEqual(restock.data["quantity_available"], 15)
        self.assertEqual(restock.data["sale_price"], 7000.0)

        count = self.client.post(
            f"/api/v1/mobile/inventory/{inv_id}/count/",
            {"counted_quantity": 14},
            format="json",
            **headers,
        )
        self.assertEqual(count.status_code, 200)
        self.assertEqual(count.data["count"], 14)
        self.assertEqual(count.data["variance"], -1)

    def test_staff_management_and_permissions_isolation(self):
        owner_headers = self._login_headers("owner2@phase2.com", "OwnerPassword123!", self.branch_a.id)

        # Create staff in Branch A with inventory permission only
        created = self.client.post(
            "/api/v1/mobile/staff/",
            {
                "email": "staffA@phase2.com",
                "first_name": "Tina",
                "last_name": "Rep",
                "role": "sales",
                "branch_id": str(self.branch_a.id),
                "permissions": ["inventory"],
            },
            format="json",
            **owner_headers,
        )
        self.assertEqual(created.status_code, 201)
        membership_id = created.data["id"]
        temp_pw = created.data["temporary_password"]

        # Staff logs in -> must_change_password=True, changes password
        login_resp = self.client.post(
            "/api/v1/mobile/auth/login/",
            {"email": "staffa@phase2.com", "password": temp_pw},
            format="json",
        )
        self.assertTrue(login_resp.data["must_change_password"])
        chg = self.client.post(
            "/api/v1/mobile/auth/change-password/",
            {"new_password": "TinaNewPassword123!", "confirm_password": "TinaNewPassword123!"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {login_resp.data['access']}",
        )
        self.assertEqual(chg.status_code, 200)
        staff_headers = {
            "HTTP_AUTHORIZATION": f"Bearer {chg.data['access']}",
            "HTTP_X_ORGANIZATION_ID": str(self.org.id),
            "HTTP_X_BRANCH_ID": str(self.branch_a.id),
        }

        # Staff has inventory access, but NOT products or staff management
        self.assertEqual(self.client.get("/api/v1/mobile/inventory/", **staff_headers).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/mobile/products/", **staff_headers).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/mobile/staff/", **staff_headers).status_code, 403)

        # Owner grants products permission and verifies
        patched = self.client.patch(
            f"/api/v1/mobile/staff/{membership_id}/",
            {"permissions": ["inventory", "products"]},
            format="json",
            **owner_headers,
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/mobile/products/", **staff_headers).status_code, 200)

    def test_reports_activity_logs_and_subscriptions(self):
        headers = self._login_headers("owner2@phase2.com", "OwnerPassword123!", self.branch_a.id)

        report = self.client.get("/api/v1/mobile/reports/sales-summary/", **headers)
        self.assertEqual(report.status_code, 200)
        self.assertIn("total_revenue", report.data)

        logs = self.client.get("/api/v1/mobile/activity-logs/", **headers)
        self.assertEqual(logs.status_code, 200)

        tickets = self.client.get("/api/v1/mobile/error-tickets/", **headers)
        self.assertEqual(tickets.status_code, 200)

        sub = self.client.get("/api/v1/mobile/subscriptions/current/", **headers)
        self.assertEqual(sub.status_code, 200)
        self.assertTrue(sub.data["is_active"])

        plans = self.client.get("/api/v1/mobile/subscriptions/plans/", **headers)
        self.assertEqual(plans.status_code, 200)
        self.assertGreaterEqual(len(plans.data), 1)


class MobileApiPhase3Tests(TestCase):
    def setUp(self):
        from decimal import Decimal
        from store.models import OnlineOrder, OnlineOrderItem, StoreListing

        self.Decimal = Decimal
        self.client = APIClient()
        self.org = Organization.objects.create(
            name="Phase3 Store",
            business_type="Retail",
            country="Nigeria",
            is_active=True,
        )
        self.branch = Branch.objects.create(
            organization=self.org,
            name="Main Branch",
            address="10 Store Way",
        )
        self.org.default_branch = self.branch
        self.org.save(update_fields=["default_branch"])

        self.plan, _ = Plan.objects.get_or_create(
            tier="basic",
            size="starter",
            billing_frequency="monthly",
            defaults={
                "name": "Starter Monthly",
                "price": 1000,
                "price_usd": 5,
                "duration_in_days": 30,
            },
        )
        Subscription.objects.create(
            organization=self.org,
            plan=self.plan,
            currency="NGN",
            start_date=timezone.now() - timedelta(days=1),
            end_date=timezone.now() + timedelta(days=29),
            is_active=True,
        )
        self.owner = CustomUser.objects.create_user(
            email="owner3@phase3.com",
            password="OwnerPassword123!",
            first_name="Ada",
            last_name="Owner",
            organization=self.org,
            branch=self.branch,
            role="owner",
            is_active=True,
        )
        self.org.owned_by = self.owner
        self.org.save(update_fields=["owned_by"])
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            branch=self.branch,
            role="owner",
            is_active=True,
        )

        self.category = Category.objects.create(
            organization=self.org,
            branch=self.branch,
            category_name="Gadgets",
        )
        self.product = Product.objects.create(
            organization=self.org,
            branch=self.branch,
            category=self.category,
            product_name="Smart Watch",
            product_code="SW-100",
            unit="pcs",
        )
        self.inv = Inventory.objects.create(
            organization=self.org,
            branch=self.branch,
            product=self.product,
            quantity=10,
            quantity_available=10,
            store=10,
            cost_price=15000.0,
            sale_price=25000.0,
        )
        self.store, _ = StoreListing.objects.get_or_create(
            organization=self.org,
            defaults={"branch": self.branch},
        )
        self.order = OnlineOrder.objects.create(
            organization=self.org,
            branch=self.branch,
            buyer_name="Chidi Buyer",
            buyer_email="chidi@example.com",
            payment_method="squadco",
            payment_status="paid",
            paid_at=timezone.now(),
            subtotal=Decimal("50000.00"),
            total_amount=Decimal("50000.00"),
        )
        OnlineOrderItem.objects.create(
            order=self.order,
            inventory=self.inv,
            product_name="Smart Watch",
            unit_price=Decimal("25000.00"),
            quantity=2,
            total_price=Decimal("50000.00"),
        )

    def _headers(self):
        resp = self.client.post(
            "/api/v1/mobile/auth/login/",
            {"email": "owner3@phase3.com", "password": "OwnerPassword123!"},
            format="json",
        )
        return {
            "HTTP_AUTHORIZATION": f"Bearer {resp.data['access']}",
            "HTTP_X_ORGANIZATION_ID": str(self.org.id),
            "HTTP_X_BRANCH_ID": str(self.branch.id),
        }

    def test_store_settings_and_listings(self):
        headers = self._headers()
        settings_resp = self.client.patch(
            "/api/v1/mobile/store/settings/",
            {"tagline": "Best Gadgets Online", "is_active": True},
            format="json",
            **headers,
        )
        self.assertEqual(settings_resp.status_code, 200)
        self.assertEqual(settings_resp.data["tagline"], "Best Gadgets Online")

        listings = self.client.get("/api/v1/mobile/store/listings/", **headers)
        self.assertEqual(listings.status_code, 200)
        self.assertEqual(len(listings.data), 1)
        listing_id = listings.data[0]["id"]
        self.assertEqual(listings.data[0]["display_title"], "Smart Watch")

        patched = self.client.patch(
            f"/api/v1/mobile/store/listings/{listing_id}/",
            {"featured": True, "custom_title": "Smart Watch Pro"},
            format="json",
            **headers,
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.data["display_title"], "Smart Watch Pro")
        self.assertTrue(patched.data["featured"])

    def test_online_order_confirm_dispatch_deliver(self):
        headers = self._headers()
        orders = self.client.get("/api/v1/mobile/store/orders/", **headers)
        self.assertEqual(orders.status_code, 200)
        self.assertEqual(orders.data["count"], 1)
        self.assertEqual(len(orders.data["results"]), 1)

        confirm = self.client.post(
            f"/api/v1/mobile/store/orders/{self.order.id}/action/",
            {"action": "confirm"},
            format="json",
            **headers,
        )
        self.assertEqual(confirm.status_code, 200)
        self.assertEqual(confirm.data["status"], "confirmed")
        self.assertIsNotNone(confirm.data["sale_id"])

        dispatch = self.client.post(
            f"/api/v1/mobile/store/orders/{self.order.id}/action/",
            {"action": "dispatch", "courier_name": "DHL", "tracking_number": "TRK-99"},
            format="json",
            **headers,
        )
        self.assertEqual(dispatch.status_code, 200)
        self.assertEqual(dispatch.data["status"], "dispatched")

        deliver = self.client.post(
            f"/api/v1/mobile/store/orders/{self.order.id}/action/",
            {"action": "deliver"},
            format="json",
            **headers,
        )
        self.assertEqual(deliver.status_code, 200)
        self.assertEqual(deliver.data["status"], "delivered")

    def test_services_wallet_and_idempotent_payouts(self):
        headers = self._headers()
        svc = self.client.post(
            "/api/v1/mobile/store/services/",
            {
                "title": "Retail Masterclass",
                "price_ngn": "10000.00",
                "price_usd": "10.00",
                "access_link": "https://zoom.us/j/123456",
            },
            format="json",
            **headers,
        )
        self.assertEqual(svc.status_code, 201)

        enr = self.client.get("/api/v1/mobile/store/services/enrollments/", **headers)
        self.assertEqual(enr.status_code, 200)

        bank = self.client.patch(
            "/api/v1/mobile/store/bank-account/",
            {
                "bank_name": "GTBank",
                "account_number": "0123456789",
                "account_name": "Phase3 Store Ltd",
            },
            format="json",
            **headers,
        )
        self.assertEqual(bank.status_code, 200)

        wallet = self.client.get("/api/v1/mobile/store/wallet/", **headers)
        self.assertEqual(wallet.status_code, 200)
        self.assertGreaterEqual(wallet.data["available_balance"], 50000.0)

        payout_payload = {
            "amount": "20000.00",
            "notes": "Weekly settlement",
            "idempotency_key": "PAYOUT-IDEM-001",
        }
        p1 = self.client.post(
            "/api/v1/mobile/store/payouts/",
            payout_payload,
            format="json",
            **headers,
        )
        self.assertEqual(p1.status_code, 201)
        self.assertFalse(p1.data["idempotent"])

        p2 = self.client.post(
            "/api/v1/mobile/store/payouts/",
            payout_payload,
            format="json",
            **headers,
        )
        self.assertEqual(p2.status_code, 200)
        self.assertTrue(p2.data["idempotent"])
        self.assertEqual(p2.data["payout"]["id"], p1.data["payout"]["id"])

    def test_price_audit_tickets_profit_report_count_and_store_extras(self):
        headers = self._headers()

        # Restock to generate a price audit entry
        restock = self.client.post(
            f"/api/v1/mobile/inventory/{self.inv.id}/restock/",
            {"quantity_added": 4, "cost_price": 16000, "sale_price": 26000},
            format="json",
            **headers,
        )
        self.assertEqual(restock.status_code, 200)

        audit = self.client.get("/api/v1/mobile/price-audit/", **headers)
        self.assertEqual(audit.status_code, 200)
        self.assertGreaterEqual(audit.data["count"], 1)
        self.assertEqual(audit.data["results"][0]["quantity_restocked"], 4)

        # Bulk count & count sheet
        bulk = self.client.post(
            "/api/v1/mobile/count/bulk/",
            {"items": [{"inventory_id": str(self.inv.id), "counted_quantity": 13}]},
            format="json",
            **headers,
        )
        self.assertEqual(bulk.status_code, 200)
        self.assertEqual(bulk.data["updated_count"], 1)

        sheet = self.client.get("/api/v1/mobile/count/", **headers)
        self.assertEqual(sheet.status_code, 200)
        self.assertEqual(sheet.data["total_items_counted"], 1)
        self.assertEqual(sheet.data["items"][0]["count"], 13)
        self.assertEqual(sheet.data["items"][0]["expected_quantity"], 14)
        self.assertEqual(sheet.data["items"][0]["variance"], -1)

        # Profit report (checkout 1 unit first)
        sale_resp = self.client.post(
            "/api/v1/mobile/pos/checkout/",
            {"method": "Cash", "items": [{"inventory_id": str(self.inv.id), "quantity": 1}]},
            format="json",
            **headers,
        )
        self.assertEqual(sale_resp.status_code, 200)
        sale_id = sale_resp.data["id"]

        profit_report = self.client.get("/api/v1/mobile/reports/profit/", **headers)
        self.assertEqual(profit_report.status_code, 200)
        self.assertEqual(profit_report.data["total_revenue"], 26000.0)
        self.assertEqual(profit_report.data["total_profit"], 10000.0)

        sale_profit = self.client.get(f"/api/v1/mobile/reports/profit/sale/{sale_id}/", **headers)
        self.assertEqual(sale_profit.status_code, 200)
        self.assertEqual(sale_profit.data["total_profit"], 10000.0)

        # Tickets: create, comment, update status
        ticket = self.client.post(
            "/api/v1/mobile/tickets/",
            {"title": "Printer offline", "description": "Thermal printer disconnected"},
            format="json",
            **headers,
        )
        self.assertEqual(ticket.status_code, 201)
        ticket_id = ticket.data["id"]

        comment = self.client.post(
            f"/api/v1/mobile/tickets/{ticket_id}/comments/",
            {"content": "Checking cable now"},
            format="json",
            **headers,
        )
        self.assertEqual(comment.status_code, 201)

        patch_ticket = self.client.patch(
            f"/api/v1/mobile/tickets/{ticket_id}/",
            {"status": "Seen"},
            format="json",
            **headers,
        )
        self.assertEqual(patch_ticket.status_code, 200)
        self.assertEqual(patch_ticket.data["status"], "Seen")
        self.assertEqual(len(patch_ticket.data["comments"]), 1)

        # Store discounts & customers
        disc = self.client.post(
            "/api/v1/mobile/store/discounts/",
            {"code": "SAVE20", "label": "Launch Promo", "discount_type": "percent", "value": "20.00"},
            format="json",
            **headers,
        )
        self.assertEqual(disc.status_code, 201)
        self.assertEqual(disc.data["code"], "SAVE20")

        customers = self.client.get("/api/v1/mobile/store/customers/", **headers)
        self.assertEqual(customers.status_code, 200)
        self.assertEqual(len(customers.data), 1)
        self.assertEqual(customers.data[0]["email"], "chidi@example.com")

        # Pagination check on activity-logs (?page=1&page_size=2 and ?page=2&page_size=2)
        from account.models import ActivityLog
        for i in range(5):
            ActivityLog.objects.create(
                organization=self.org,
                branch=self.branch,
                staff=self.owner,
                activity=f"Pagination log {i}",
            )
        page1 = self.client.get("/api/v1/mobile/activity-logs/?page=1&page_size=2", **headers)
        self.assertEqual(page1.status_code, 200)
        self.assertGreaterEqual(page1.data["count"], 5)
        self.assertEqual(len(page1.data["results"]), 2)
        self.assertIsNotNone(page1.data["next"])
        self.assertIsNone(page1.data["previous"])

        page2 = self.client.get("/api/v1/mobile/activity-logs/?page=2&page_size=2", **headers)
        self.assertEqual(page2.status_code, 200)
        self.assertEqual(len(page2.data["results"]), 2)
        self.assertIsNotNone(page2.data["previous"])

        # Uncounted items report no variance, even if quantity_available drifts from store_quantity
        self.inv.count = None
        self.inv.quantity = 10
        self.inv.quantity_available = 14
        self.inv.save(update_fields=["count", "quantity", "quantity_available"])
        sheet_uncounted = self.client.get("/api/v1/mobile/count/", **headers)
        self.assertEqual(sheet_uncounted.status_code, 200)
        self.assertEqual(sheet_uncounted.data["total_items_counted"], 0)
        self.assertEqual(sheet_uncounted.data["items_with_variance"], 0)
        self.assertEqual(sheet_uncounted.data["total_variance_qty"], 0)
        self.assertIsNone(sheet_uncounted.data["items"][0]["variance"])




