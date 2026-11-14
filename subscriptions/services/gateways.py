import hashlib
import hmac
import logging
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SUPPORTED_GATEWAYS = ("bachs", "squadco")


def parse_decimal_amount(value, field_name="amount"):
    """Parse a value into a finite Decimal, raising ValueError on invalid or non-finite input."""
    if value is None or isinstance(value, bool):
        raise ValueError(f"Invalid {field_name}: value is required.")
    try:
        dec = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {field_name}: {value!r}") from exc
    if not dec.is_finite():
        raise ValueError(f"Invalid {field_name}: non-finite number.")
    return dec


def validate_positive_amount(value, field_name="amount", allow_zero=False):
    """
    Validate that a monetary figure is finite and strictly positive (> 0),
    or >= 0 when allow_zero=True. Rejects negative numbers like -1000, NaN, Infinity.
    """
    dec = parse_decimal_amount(value, field_name=field_name)
    if allow_zero:
        if dec < Decimal("0.00"):
            raise ValueError(f"{field_name} cannot be negative.")
    else:
        if dec <= Decimal("0.00"):
            raise ValueError(f"{field_name} must be greater than zero.")
    return dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def verify_amount_and_currency(expected_amount, expected_currency, paid_amount, paid_currency):
    """
    Verify gateway-reported amount and currency match expectations.
    Returns (ok: bool, reason: str).
    """
    try:
        expected_dec = validate_positive_amount(expected_amount, field_name="expected_amount")
    except ValueError as exc:
        return False, str(exc)

    if paid_amount is None:
        return False, "Gateway did not return a confirmed payment amount."
    try:
        paid_dec = validate_positive_amount(paid_amount, field_name="paid_amount")
    except ValueError as exc:
        return False, str(exc)

    exp_curr = (expected_currency or "").strip().upper()
    paid_curr = (paid_currency or "").strip().upper()
    if exp_curr and paid_curr and paid_curr != exp_curr:
        return False, f"Currency mismatch: expected {exp_curr}, got {paid_curr}."

    if paid_dec < expected_dec:
        return False, f"Underpayment detected: expected {expected_dec} {exp_curr}, got {paid_dec} {paid_curr}."

    return True, "OK"


class BachsGateway:
    """
    Client for Bachs (bachs.io) REST API:
    - Checkout Sessions (/v1/checkout-sessions)
    - Payout Destinations (/v1/payouts/destinations)
    - Payouts (/v1/payouts)
    - Webhook V2 Signature Verification (X-Bachs-Signature-V2)
    """

    name = "bachs"

    def __init__(self, api_key=None, base_url=None, webhook_secret=None):
        self.api_key = (api_key if api_key is not None else getattr(settings, "BACHS_API_KEY", "")).strip()
        default_base = "https://api.bachs.io" if self.api_key.startswith("sk_live_") else "https://sandbox-api.bachs.io"
        self.base_url = (base_url if base_url is not None else getattr(settings, "BACHS_API_BASE_URL", default_base)).strip().rstrip("/")
        self.webhook_secret = (webhook_secret if webhook_secret is not None else getattr(settings, "BACHS_WEBHOOK_SECRET", "")).strip()

    def validate_config(self):
        if not self.api_key:
            return False, "Bachs API key is missing. Set BACHS_API_KEY in environment."
        if not self.base_url:
            return False, "Bachs API base URL is missing. Set BACHS_API_BASE_URL in environment."
        return True, "OK"

    def _headers(self, idempotency_key=None):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = str(idempotency_key)[:128]
        return headers

    def create_checkout(
        self,
        amount,
        currency,
        customer_email,
        customer_name,
        reference,
        metadata=None,
        success_url=None,
        cancel_url=None,
        timeout=20,
    ):
        ok, msg = self.validate_config()
        if not ok:
            raise RuntimeError(msg)

        amt = validate_positive_amount(amount, field_name="checkout amount")
        curr = (currency or "NGN").strip().upper()
        if len(curr) != 3:
            raise ValueError(f"Invalid ISO currency code: {curr!r}")

        safe_metadata = {}
        if isinstance(metadata, dict):
            # Bachs supports up to 20 metadata key-value pairs (string values).
            for k, v in list(metadata.items())[:20]:
                if v is not None:
                    safe_metadata[str(k)] = str(v)

        payload = {
            "pricing": {
                "amount": f"{amt:.2f}",
                "currency": curr,
            },
            "customer": {
                "email": (customer_email or "").strip(),
                "name": (customer_name or customer_email or "Customer").strip(),
            },
            "metadata": safe_metadata,
        }
        if success_url:
            payload["success_url"] = success_url
        if cancel_url:
            payload["cancel_url"] = cancel_url

        resp = requests.post(
            f"{self.base_url}/v1/checkout-sessions",
            headers=self._headers(idempotency_key=f"chk-{reference}"),
            json=payload,
            timeout=timeout,
        )
        if resp.status_code not in (200, 201):
            err_msg = self._extract_error(resp)
            raise RuntimeError(f"Bachs checkout error ({resp.status_code}): {err_msg}")

        data = resp.json()
        checkout_id = data.get("checkout_id") or data.get("id")
        checkout_url = data.get("checkout_url") or data.get("url")
        if not checkout_id or not checkout_url:
            raise RuntimeError("Bachs did not return checkout_id and checkout_url.")

        return {
            "checkout_id": checkout_id,
            "checkout_url": checkout_url,
            "reference": reference,
            "raw": data,
        }

    def verify_checkout(self, checkout_id, timeout=20):
        ok, msg = self.validate_config()
        if not ok:
            raise RuntimeError(msg)
        if not checkout_id:
            raise ValueError("checkout_id is required.")

        resp = requests.get(
            f"{self.base_url}/v1/checkout-sessions/{checkout_id}",
            headers=self._headers(),
            timeout=timeout,
        )
        if resp.status_code != 200:
            err_msg = self._extract_error(resp)
            raise RuntimeError(f"Bachs verify error ({resp.status_code}): {err_msg}")

        data = resp.json()
        status = str(data.get("status") or "").strip().lower()
        paid_statuses = {"completed", "paid", "succeeded", "success"}
        raw_amount = data.get("amount") or (data.get("pricing") or {}).get("amount")
        raw_currency = data.get("currency") or (data.get("pricing") or {}).get("currency") or ""
        parsed_amount = None
        if raw_amount is not None:
            try:
                parsed_amount = parse_decimal_amount(raw_amount, field_name="gateway amount")
            except ValueError:
                parsed_amount = None

        return {
            "is_paid": status in paid_statuses,
            "status": status,
            "amount": parsed_amount,
            "currency": str(raw_currency).strip().upper(),
            "checkout_id": data.get("checkout_id") or checkout_id,
            "metadata": data.get("metadata") or {},
            "raw": data,
        }

    def create_payout_destination(
        self,
        currency,
        account_number,
        bank_code,
        name,
        dest_type="bank_account",
        timeout=20,
    ):
        ok, msg = self.validate_config()
        if not ok:
            raise RuntimeError(msg)

        curr = (currency or "NGN").strip().upper()
        acct = str(account_number or "").strip()
        bcode = str(bank_code or "").strip()
        if not acct or not bcode:
            raise ValueError("Both account_number and bank_code are required to register a Bachs destination.")

        idem = hashlib.sha256(f"{curr}:{bcode}:{acct}:{name}".encode("utf-8")).hexdigest()[:32]
        payload = {
            "type": dest_type,
            "currency": curr,
            "account_number": acct,
            "bank_code": bcode,
            "name": (name or "Merchant Settlement Account").strip()[:100],
        }
        resp = requests.post(
            f"{self.base_url}/v1/payouts/destinations",
            headers=self._headers(idempotency_key=f"dest-{idem}"),
            json=payload,
            timeout=timeout,
        )
        if resp.status_code not in (200, 201):
            err_msg = self._extract_error(resp)
            raise RuntimeError(f"Bachs destination error ({resp.status_code}): {err_msg}")

        data = resp.json()
        dest_id = data.get("id") or data.get("destination_id")
        if not dest_id:
            raise RuntimeError("Bachs did not return a destination ID.")

        return {
            "destination_id": dest_id,
            "is_usable": bool(data.get("is_usable", True)),
            "raw": data,
        }

    def resolve_bank_account(self, account_number, bank_code, timeout=12):
        ok, msg = self.validate_config()
        if not ok:
            raise RuntimeError(msg)

        acct = str(account_number or "").strip()
        bcode = str(bank_code or "").strip()
        if not acct or not bcode:
            raise ValueError("Both account_number and bank_code are required.")

        resp = requests.post(
            f"{self.base_url}/v1/misc/bank-accounts/resolve",
            headers=self._headers(),
            json={"account_number": acct, "bank_code": bcode},
            timeout=timeout,
        )
        if resp.status_code != 200:
            err_msg = self._extract_error(resp)
            raise RuntimeError(f"Bachs bank resolve error ({resp.status_code}): {err_msg}")

        data = resp.json()
        account_name = (data.get("account_name") or "").strip()
        if not account_name:
            raise RuntimeError("Bachs did not return an account_name.")
        return {
            "resolved": bool(data.get("resolved", True)),
            "account_name": account_name,
            "account_number": data.get("account_number") or acct,
            "raw": data,
        }

    def create_payout(
        self,
        destination_id,
        amount,
        reference,
        narration="",
        idempotency_key=None,
        timeout=20,
    ):
        ok, msg = self.validate_config()
        if not ok:
            raise RuntimeError(msg)
        if not destination_id:
            raise ValueError("destination_id is required for Bachs payout.")

        amt = validate_positive_amount(amount, field_name="payout amount")
        idem = (idempotency_key or reference).strip()
        payload = {
            "destination": destination_id,
            "amount": f"{amt:.2f}",
            "reference": str(reference),
            "narration": (narration or f"Payout {reference}")[:140],
        }
        resp = requests.post(
            f"{self.base_url}/v1/payouts",
            headers=self._headers(idempotency_key=f"pay-{idem}"),
            json=payload,
            timeout=timeout,
        )
        if resp.status_code not in (200, 201, 202):
            err_msg = self._extract_error(resp)
            raise RuntimeError(f"Bachs payout error ({resp.status_code}): {err_msg}")

        data = resp.json()
        return {
            "payout_id": data.get("id") or data.get("payout_id") or str(reference),
            "status": str(data.get("status") or "processing").lower(),
            "raw": data,
        }

    def verify_webhook_signature(self, raw_body, signature_header, timestamp_header=None, tolerance_seconds=300):
        """
        Verify Bachs webhook HMAC-SHA256 signature:
        - Supports `X-Bachs-Signature-V2` (`t=<ts>,v1=<hex>[,v1=<hex>]`)
        - Supports `Bachs-Signature` (`t=<ts>,v1=<hex>` or raw HMAC-SHA256 hex digest with optional `X-Bachs-Timestamp`)
        Uses constant-time comparison and 300s replay tolerance.
        Returns (ok: bool, reason: str).
        """
        if not self.webhook_secret:
            return False, "BACHS_WEBHOOK_SECRET is not configured."
        if not signature_header:
            return False, "Missing Bachs signature header."

        sig_str = str(signature_header).strip()
        body_bytes = raw_body if isinstance(raw_body, (bytes, bytearray)) else str(raw_body).encode("utf-8")
        body_str = body_bytes.decode("utf-8")

        # V2 format: t=<ts>,v1=<hex>[,v1=<hex>]
        if "v1=" in sig_str:
            timestamp_str = None
            v1_signatures = []
            for part in sig_str.split(","):
                key, _, val = part.strip().partition("=")
                if key == "t":
                    timestamp_str = val.strip()
                elif key == "v1":
                    v1_signatures.append(val.strip())

            if not timestamp_str or not v1_signatures:
                return False, "Malformed X-Bachs-Signature-V2 header."

            try:
                ts = int(timestamp_str)
            except ValueError:
                return False, "Invalid webhook timestamp."

            if abs(int(time.time()) - ts) > tolerance_seconds:
                return False, "Webhook timestamp outside replay tolerance window."

            signed_payload = f"{timestamp_str}.{body_str}".encode("utf-8")
            expected_sig = hmac.new(
                self.webhook_secret.encode("utf-8"),
                signed_payload,
                hashlib.sha256,
            ).hexdigest()

            for sig in v1_signatures:
                if hmac.compare_digest(sig, expected_sig):
                    return True, "OK"

            return False, "Signature mismatch."

        # Plain hex HMAC-SHA256 format (`Bachs-Signature`)
        if timestamp_header:
            try:
                ts = int(str(timestamp_header).strip())
            except ValueError:
                return False, "Invalid webhook timestamp."
            if abs(int(time.time()) - ts) > tolerance_seconds:
                return False, "Webhook timestamp outside replay tolerance window."
            signed_payload = f"{ts}.{body_str}".encode("utf-8")
            expected_sig = hmac.new(self.webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
            if hmac.compare_digest(sig_str, expected_sig):
                return True, "OK"

        expected_raw = hmac.new(self.webhook_secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig_str, expected_raw):
            return True, "OK"

        return False, "Signature mismatch."

    @staticmethod
    def _extract_error(resp):
        try:
            body = resp.json()
            return body.get("message") or body.get("detail") or body.get("error") or resp.text[:250]
        except Exception:
            return (resp.text or "")[:250]


class SquadGateway:
    """Wrapper around SquadCo API operations."""

    name = "squadco"

    def __init__(self, secret_key=None, merchant_id=None, base_url=None):
        self.secret_key = (secret_key if secret_key is not None else getattr(settings, "SQUAD_SECRET_KEY", "")).strip()
        self.merchant_id = (merchant_id if merchant_id is not None else getattr(settings, "SQUAD_MERCHANT_ID", "")).strip()
        self.base_url = (base_url if base_url is not None else getattr(settings, "SQUAD_API_BASE_URL", "")).strip().rstrip("/")

    def _headers(self):
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }
        if self.merchant_id:
            headers["MerchantId"] = self.merchant_id
        return headers

    def validate_config(self):
        if not self.secret_key:
            return False, "SquadCo secret key is missing. Set SQUAD_SECRET_KEY in environment."
        if not self.base_url:
            return False, "SquadCo API base URL is missing. Set SQUAD_API_BASE_URL in environment."
        return True, "OK"

    def verify_webhook_signature(self, raw_body, signature_header):
        if not self.secret_key or not signature_header:
            return False
        payload = raw_body if isinstance(raw_body, (bytes, bytearray)) else str(raw_body).encode("utf-8")
        expected = hmac.new(self.secret_key.encode("utf-8"), payload, hashlib.sha512).hexdigest()
        return hmac.compare_digest(str(signature_header), expected)


def get_active_gateway_name():
    """Return the active gateway name configured in Django Admin (`bachs` by default)."""
    from subscriptions.models import PaymentGatewayConfig
    return PaymentGatewayConfig.get_active_gateway()


def get_gateway_client(gateway_name=None):
    """Return the configured gateway client instance for `gateway_name` or active default."""
    name = (gateway_name or get_active_gateway_name() or "bachs").strip().lower()
    if name == "squadco":
        return SquadGateway()
    return BachsGateway()


def build_public_url(request, path):
    """
    Build a publicly accessible URL for gateway redirects (success_url / cancel_url).
    Uses settings.PUBLIC_BASE_URL when set (e.g. ngrok URL during local dev),
    otherwise uses request.build_absolute_uri(path) and upgrades ngrok URLs to https.
    """
    public_base = (getattr(settings, "PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    if public_base:
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{public_base}{path}"

    url = request.build_absolute_uri(path)
    if url.startswith("http://") and any(h in url for h in (".ngrok-free.", ".ngrok.io")):
        url = "https://" + url[len("http://"):]
    return url

