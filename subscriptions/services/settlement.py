from decimal import Decimal
from django.db.models import Sum


def get_platform_settlement_summary():
    """
    Compute the exact breakdown between:
    1. Quicksales platform revenue (subscriptions) — safe for Quicksales to settle.
    2. Customer/vendor online store & class funds — held on behalf of merchants for withdrawal.

    Returns a dictionary keyed by currency (e.g. 'NGN', 'USD') plus a list of rows.
    """
    from subscriptions.models import Payment
    from store.models import OnlineOrder, ServiceEnrollment, StorePayout

    gateway_methods = ("bachs", "squadco")

    # 1. Quicksales Subscription Revenue (100% belongs to Quicksales)
    sub_rows = (
        Payment.objects.filter(payment_status="completed", payment_method__in=gateway_methods)
        .values("currency", "payment_method")
        .annotate(total=Sum("amount"))
    )

    # 2. Customer Online Store Orders (belongs to Vendors/Customers)
    order_rows = (
        OnlineOrder.objects.filter(payment_status="paid", payment_method__in=gateway_methods)
        .values("currency", "payment_method")
        .annotate(total=Sum("total_amount"))
    )

    # 3. Customer Class / Service Enrollments (settled in NGN wallet or native currency)
    service_ngn_total = (
        ServiceEnrollment.objects.filter(payment_status="paid")
        .aggregate(total=Sum("settled_amount_ngn"))["total"]
        or Decimal("0.00")
    )

    # 4. Vendor Payouts (Completed & Pending/Processing)
    completed_payout_rows = (
        StorePayout.objects.filter(status="completed")
        .values("currency")
        .annotate(total=Sum("amount"))
    )
    pending_payout_rows = (
        StorePayout.objects.filter(status__in=["pending", "processing"])
        .values("currency")
        .annotate(total=Sum("amount"))
    )

    currencies = set()
    by_currency = {}

    def _bucket(curr):
        c = (curr or "NGN").upper()
        currencies.add(c)
        if c not in by_currency:
            by_currency[c] = {
                "currency": c,
                "platform_bachs": Decimal("0.00"),
                "platform_squadco": Decimal("0.00"),
                "platform_total": Decimal("0.00"),
                "customer_orders_bachs": Decimal("0.00"),
                "customer_orders_squadco": Decimal("0.00"),
                "customer_services": Decimal("0.00"),
                "customer_gross": Decimal("0.00"),
                "customer_paid_out": Decimal("0.00"),
                "customer_pending_payouts": Decimal("0.00"),
                "customer_withdrawable_held": Decimal("0.00"),
                "customer_available_to_request": Decimal("0.00"),
                "expected_gateway_balance": Decimal("0.00"),
                "safe_to_settle_ours": Decimal("0.00"),
            }
        return by_currency[c]

    for row in sub_rows:
        b = _bucket(row["currency"])
        amt = row["total"] or Decimal("0.00")
        if row["payment_method"] == "bachs":
            b["platform_bachs"] += amt
        elif row["payment_method"] == "squadco":
            b["platform_squadco"] += amt
        b["platform_total"] += amt

    for row in order_rows:
        b = _bucket(row["currency"])
        amt = row["total"] or Decimal("0.00")
        if row["payment_method"] == "bachs":
            b["customer_orders_bachs"] += amt
        elif row["payment_method"] == "squadco":
            b["customer_orders_squadco"] += amt
        b["customer_gross"] += amt

    if service_ngn_total > Decimal("0.00"):
        b_ngn = _bucket("NGN")
        b_ngn["customer_services"] += service_ngn_total
        b_ngn["customer_gross"] += service_ngn_total

    for row in completed_payout_rows:
        b = _bucket(row["currency"])
        b["customer_paid_out"] += row["total"] or Decimal("0.00")

    for row in pending_payout_rows:
        b = _bucket(row["currency"])
        b["customer_pending_payouts"] += row["total"] or Decimal("0.00")

    # Always include NGN and USD buckets at minimum
    _bucket("NGN")
    _bucket("USD")

    for b in by_currency.values():
        b["customer_withdrawable_held"] = max(
            Decimal("0.00"), b["customer_gross"] - b["customer_paid_out"]
        )
        b["customer_available_to_request"] = max(
            Decimal("0.00"),
            b["customer_gross"] - b["customer_paid_out"] - b["customer_pending_payouts"],
        )
        b["expected_gateway_balance"] = b["platform_total"] + b["customer_withdrawable_held"]
        b["safe_to_settle_ours"] = b["platform_total"]

    ordered = [by_currency[c] for c in sorted(by_currency.keys(), key=lambda x: (x != "NGN", x != "USD", x))]
    return {
        "by_currency": by_currency,
        "rows": ordered,
    }

