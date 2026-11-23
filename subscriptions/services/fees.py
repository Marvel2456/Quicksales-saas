from decimal import Decimal, ROUND_HALF_UP


BACHS_FEE_RULES_SUMMARY = [
    {
        "channel": "NGN Bank Transfer (Checkout)",
        "fee": "1.5% (capped at ₦2,000) — Shared 50/50",
        "notes": "Buyer pays 0.75% (capped at ₦1,000) as a Service Charge at checkout; seller covers the remaining half.",
    },
    {
        "channel": "NGN Local Card",
        "fee": "2.0% — Shared with Buyer",
        "notes": "Buyer pays 0.75% (capped at ₦1,000) Service Charge at checkout; seller covers the balance.",
    },
    {
        "channel": "USD / US-Issued Card",
        "fee": "5.0% + $0.40 (+$0.03 if 3DS) — Shared 50/50",
        "notes": "Buyer pays 2.5% + $0.20 as a Service Charge at checkout; seller covers the remaining half.",
    },
    {
        "channel": "International (Non-US) Card",
        "fee": "6.5% + $0.40 (+$0.03 if 3DS) — Shared with Buyer",
        "notes": "Buyer pays 2.5% + $0.20 Service Charge at checkout; seller covers the balance.",
    },
    {
        "channel": "NGN Bank Withdrawals",
        "fee": "Instant local settlement",
        "notes": "Withdrawn directly to your registered Nigerian bank account from your net NGN balance.",
    },
]


def _q2(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_buyer_service_charge(base_amount, currency: str = "NGN") -> Decimal:
    """
    Compute the buyer's 50% shared Service Charge added at online checkout.
    - NGN: 0.75% of base_amount, capped at ₦1,000.00 (half of 1.5% cap ₦2,000)
    - USD: 2.5% + $0.20 (half of 5.0% + $0.40)
    """
    amt = Decimal(str(base_amount or "0.00"))
    if amt <= Decimal("0.00"):
        return Decimal("0.00")

    curr = (currency or "NGN").strip().upper()
    if curr == "NGN":
        return min(_q2(amt * Decimal("0.0075")), Decimal("1000.00"))
    if curr == "USD":
        return _q2((amt * Decimal("0.05") + Decimal("0.40")) / Decimal("2"))
    return _q2(amt * Decimal("0.01"))


def normalize_bachs_channel(raw_channel: str | None, currency: str = "NGN") -> str:
    """Normalize a Bachs payment method/channel string into a canonical key."""
    curr = (currency or "NGN").strip().upper()
    ch = str(raw_channel or "").strip().lower()
    if not ch:
        return "card" if curr == "USD" else "bank_transfer"
    if "virtual" in ch or "va" == ch:
        return "virtual_account"
    if "crypto" in ch or "usdt" in ch or "usdc" in ch or "stablecoin" in ch:
        return "crypto"
    if "card" in ch:
        return "card"
    if "transfer" in ch or "bank" in ch:
        return "bank_transfer"
    return "card" if curr == "USD" else "bank_transfer"


def calculate_bachs_collection_fee(
    amount,
    currency: str = "NGN",
    channel: str = "bank_transfer",
    is_non_us_card: bool = False,
    has_3ds: bool = False,
) -> Decimal:
    """
    Compute the Bachs inbound processing fee for a paid order or enrollment.
    """
    amt = Decimal(str(amount or "0.00"))
    if amt <= Decimal("0.00"):
        return Decimal("0.00")

    curr = (currency or "NGN").strip().upper()
    ch = normalize_bachs_channel(channel, curr)

    if curr == "NGN":
        if ch == "card":
            fee = amt * Decimal("0.02")
        elif ch == "virtual_account":
            fee = min(amt * Decimal("0.01"), Decimal("300.00"))
        else:
            fee = min(amt * Decimal("0.015"), Decimal("2000.00"))
    elif curr == "USD":
        if ch == "crypto":
            fee = amt * Decimal("0.015")
        else:
            rate = Decimal("0.065") if is_non_us_card else Decimal("0.05")
            fixed = Decimal("0.40") + (Decimal("0.03") if has_3ds else Decimal("0.00"))
            fee = (amt * rate) + fixed
    else:
        fee = amt * Decimal("0.02")

    fee = _q2(fee)
    return min(fee, amt)


def extract_bachs_fee_details(payload: dict | None, amount, currency: str = "NGN") -> dict:
    """
    Extract (payment_channel, gateway_fee, net_amount) from a Bachs webhook or
    verify_checkout response dict, falling back to documented Bachs fee rules
    when Bachs does not explicitly return a fee field.
    """
    amt = _q2(Decimal(str(amount or "0.00")))
    curr = (currency or "NGN").strip().upper()
    data = payload if isinstance(payload, dict) else {}

    raw_channel = (
        data.get("payment_method")
        or data.get("payment_method_type")
        or data.get("channel")
        or (data.get("payment") or {}).get("method")
        or (data.get("payment") or {}).get("channel")
    )
    channel = normalize_bachs_channel(raw_channel, curr)
    if curr == "NGN" and channel == "card":
        canonical_channel = "card_ngn"
    elif curr == "USD" and channel == "card":
        card_country = str(
            data.get("card_country")
            or (data.get("card") or {}).get("country")
            or "US"
        ).strip().upper()
        is_non_us = card_country not in ("", "US", "USA")
        canonical_channel = "card_intl" if is_non_us else "card_usd"
    else:
        is_non_us = False
        canonical_channel = channel

    has_3ds = bool(data.get("three_ds") or data.get("is_3ds") or (data.get("card") or {}).get("three_ds"))

    raw_fee = data.get("fee") or data.get("gateway_fee") or (data.get("pricing") or {}).get("fee")
    if raw_fee is not None and str(raw_fee).strip() != "":
        try:
            fee = _q2(Decimal(str(raw_fee)))
            if fee < Decimal("0.00"):
                fee = Decimal("0.00")
        except Exception:
            fee = calculate_bachs_collection_fee(
                amt, curr, channel=channel, is_non_us_card=is_non_us, has_3ds=has_3ds
            )
    else:
        fee = calculate_bachs_collection_fee(
            amt, curr, channel=channel, is_non_us_card=is_non_us, has_3ds=has_3ds
        )

    fee = min(fee, amt)
    raw_net = data.get("net_amount") or (data.get("pricing") or {}).get("net_amount")
    if raw_net is not None and str(raw_net).strip() != "":
        try:
            net_amount = _q2(Decimal(str(raw_net)))
        except Exception:
            net_amount = _q2(amt - fee)
    else:
        net_amount = _q2(amt - fee)

    return {
        "payment_channel": canonical_channel,
        "gateway_fee": fee,
        "net_amount": max(Decimal("0.00"), net_amount),
    }
