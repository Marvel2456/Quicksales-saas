from django.shortcuts import render, redirect, HttpResponse
from account.models import Organization
from .models import Subscription, Plan, Payment, Coupon, CouponRedemption
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from account.decorators import role_required
from account.utils import get_request_org_role, get_request_organization
from django.shortcuts import get_object_or_404
import requests
from django.conf import settings
from django.urls import reverse
from django.http import JsonResponse
import uuid
import json
import time
from django.utils import timezone
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from account.tasks import deactivate_subscription, task_send_subscription_success_email
from decimal import Decimal


def _squad_headers():
    headers = {
        "Authorization": f"Bearer {settings.SQUAD_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    if settings.SQUAD_MERCHANT_ID:
        headers["MerchantId"] = settings.SQUAD_MERCHANT_ID
    return headers


def _extract_checkout_url(data):
    """Handle possible SquadCo response shapes for redirect URL."""
    if not isinstance(data, dict):
        return None
    payload = data.get("data", data)
    if not isinstance(payload, dict):
        return None
    candidates = [
        payload.get("checkout_url"),
        payload.get("payment_link"),
        payload.get("redirect_link"),
        payload.get("authorization_url"),
        payload.get("url"),
    ]
    return next((value for value in candidates if value), None)


def _extract_status(data):
    """Handle possible SquadCo response status fields."""
    if not isinstance(data, dict):
        return ""
    payload = data.get("data", data)
    if not isinstance(payload, dict):
        return ""
    return str(
        payload.get("status")
        or payload.get("payment_status")
        or payload.get("transaction_status")
        or ""
    ).lower()


def _infer_checkout_url(transaction_ref):
    """Build a hosted checkout URL for a known Squad transaction reference."""
    api_base = (settings.SQUAD_API_BASE_URL or "").lower()
    checkout_host = "sandbox-pay.squadco.com" if "sandbox" in api_base else "pay.squadco.com"
    return f"https://{checkout_host}/{transaction_ref}"


def _squad_api_bases():
    """Return the Squad API base URL. No failover — the alternate sandbox endpoint
    uses different credentials and causes 403 errors."""
    configured = (settings.SQUAD_API_BASE_URL or "https://sandbox-api-d.squadco.com").rstrip("/")
    return [configured]


def _validate_squad_config():
    """Return (ok, message) for required SquadCo config."""
    secret_key = (settings.SQUAD_SECRET_KEY or "").strip()
    merchant_id = (settings.SQUAD_MERCHANT_ID or "").strip()

    if not secret_key:
        return False, "SquadCo secret key is missing. Set SQUAD_SECRET_KEY in environment."

    if secret_key.startswith("sandbox_pk_") or secret_key.startswith("live_pk_") or secret_key.startswith("pk_"):
        return False, "SquadCo keys appear swapped. Put sandbox_sk_... in SQUAD_SECRET_KEY and sandbox_pk_... in SQUAD_PUBLIC_KEY."

    # SquadCo sandbox keys are typically prefixed with sandbox_sk_
    # Keep this permissive for live keys while still catching obvious misconfiguration.
    if not (
        secret_key.startswith("sandbox_sk_")
        or secret_key.startswith("live_sk_")
        or secret_key.startswith("sk_")
    ):
        return False, "SquadCo secret key format is invalid. Expected sandbox_sk_... (or live key in production)."

    if not merchant_id:
        return False, "SquadCo merchant ID is missing. Set SQUAD_MERCHANT_ID in environment."

    return True, "ok"


def get_or_create_plan(tier, size, billing_frequency):
    """Get or create a Plan based on tier, size, and billing frequency"""
    # Define plan properties based on tier and size
    tier_upper = tier.lower()
    size_upper = size.lower()
    freq_upper = billing_frequency.lower()
    
    # Generate a meaningful name
    tier_display = dict(Plan.TIER_CHOICES).get(tier_upper, tier)
    size_display = dict(Plan.SIZE_CHOICES).get(size_upper, size)
    freq_display = dict(Plan.BILLING_FREQUENCY_CHOICES).get(freq_upper, billing_frequency)
    
    plan_name = f"{tier_display} {size_display} - {freq_display}"
    
    # Define features based on tier
    tier_features = {
        'basic': {'users': 1, 'branches': 1, 'products': 100},
        'growth': {'users': 5, 'branches': 5, 'products': 1000},
        'premium': {'users': 20, 'branches': 20, 'products': 5000}
    }
    
    # Define base prices based on tier and size
    base_prices = {
        'basic': {'starter': 15000, 'large': 25000, 'xl': 40000},
        'growth': {'starter': 35000, 'large': 60000, 'xl': 100000},
        'premium': {'starter': 80000, 'large': 150000, 'xl': 250000}
    }
    
    # Get base price
    base_price = base_prices.get(tier_upper, {}).get(size_upper, 15000)
    
    # Apply billing frequency multiplier
    freq_multipliers = {
        'monthly': 1.0,
        'quarterly': 0.95,   # 5% discount
        'annually': 0.85      # 15% discount
    }
    
    multiplier = freq_multipliers.get(freq_upper, 1.0)
    final_price = int(base_price * multiplier)
    
    # Duration in days based on frequency
    duration_map = {
        'monthly': 30,
        'quarterly': 90,
        'annually': 365
    }
    
    duration = duration_map.get(freq_upper, 30)
    
    # Get features
    features = tier_features.get(tier_upper, {'users': 1, 'branches': 1, 'products': 100})
    
    # Get or create the plan
    plan, created = Plan.objects.get_or_create(
        tier=tier_upper,
        size=size_upper,
        billing_frequency=freq_upper,
        defaults={
            'name': plan_name,
            'price': final_price,
            'duration_in_days': duration,
            'description': f"{tier_display} plan with {size_display} capacity",
            'max_users': features['users'],
            'max_branches': features['branches'],
            'max_products': features['products'],
        }
    )
    
    return plan


def apply_coupon(coupon_code, organization, plan):
    """
    Apply a coupon to a plan and return adjusted amount.
    Returns: (success: bool, amount: Decimal, message: str, coupon: Coupon or None)
    """
    try:
        coupon = Coupon.objects.get(code__iexact=coupon_code)
    except Coupon.DoesNotExist:
        return False, Decimal('0.00'), "Invalid coupon code", None

    if not coupon.is_valid():
        return False, Decimal('0.00'), "Coupon is no longer valid", coupon

    if coupon.uses >= coupon.max_uses:
        return False, Decimal('0.00'), "Coupon has reached max uses", coupon

    # Check if organization already used this coupon
    if CouponRedemption.objects.filter(coupon=coupon, organization=organization).exists():
        return False, Decimal('0.00'), "You have already used this coupon", coupon

    # Calculate discount
    original_amount = Decimal(str(plan.price))

    if coupon.type == 'percent':
        discount = (original_amount * coupon.value) / Decimal('100')
        final_amount = original_amount - discount
    elif coupon.type == 'fixed':
        discount = coupon.value
        final_amount = max(original_amount - discount, Decimal('0.00'))
    elif coupon.type == 'free_month':
        # Free month means they don't pay this month
        final_amount = Decimal('0.00')
    else:
        return False, Decimal('0.00'), "Invalid coupon type", coupon

    return True, final_amount, "Coupon applied successfully", coupon


def validate_coupon(coupon_code):
    """Validate coupon without applying discount - for frontend checks."""
    try:
        coupon = Coupon.objects.get(code__iexact=coupon_code)
    except Coupon.DoesNotExist:
        return False, "Invalid coupon code"

    if not coupon.is_valid():
        return False, "Coupon is no longer valid"

    if coupon.uses >= coupon.max_uses:
        return False, "Coupon has reached max uses"

    return True, "Valid coupon"


# Create your views here.



@login_required
def settingsView(request):
    # Get organization from middleware context
    organization = get_request_organization(request)
    
    # Check if user has an organization
    if organization is None:
        messages.error(request, "You must be part of an organization to access settings.")
        return redirect('dashboard')
    
    # Check if user has owner role in this organization
    user_role = get_request_org_role(request, organization)
    
    if user_role != 'owner':
        messages.error(request, "Only organization owners can access settings.")
        return redirect('dashboard')
    
    subscription = Subscription.objects.filter(organization=organization, is_active=True).order_by('-end_date').first()
    plans = Plan.objects.exclude(tier='free').order_by('tier', 'size', 'billing_frequency')

    context = {
        'organization': organization,
        'subscription': subscription,
        'plans': plans,
        'tier_choices': Plan.TIER_CHOICES,
        'size_choices': Plan.SIZE_CHOICES,
        'billing_frequency_choices': Plan.BILLING_FREQUENCY_CHOICES,
    }
    return render(request, 'account/settings.html', context)



@role_required(roles=['owner'])
@login_required
def editOrganization(request, pk):
    organization = get_object_or_404(Organization, id=pk, owned_by=request.user)

    if request.method == "POST":
        organization.name = request.POST.get("name", organization.name)
        organization.business_type = request.POST.get("business_type", organization.business_type)
        organization.country = request.POST.get("country", organization.country)
        organization.save()
        messages.success(request, "Organization updated successfully")
        return redirect("settings")

    return redirect("settings")


@login_required
def cancel_plan(request, subscription_id):
    # Only allow POST requests
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("settings")
    
    # Check if user has owner role
    if get_request_org_role(request, get_request_organization(request)) != 'owner':
        messages.error(request, "Only organization owners can cancel subscriptions.")
        return redirect("settings")
    
    # Get the subscription
    try:
        subscription = Subscription.objects.get(
            id=subscription_id,
            organization=get_request_organization(request),
            is_active=True
        )
    except Subscription.DoesNotExist:
        messages.error(request, "Subscription not found or already cancelled.")
        return redirect("settings")

    # Deactivate the subscription
    subscription.is_active = False
    subscription.cancelled_at = timezone.now()
    subscription.save()

    messages.success(request, "Your subscription has been cancelled successfully.")
    return redirect("settings")


@login_required
def init_payment(request, plan_id):
    config_ok, config_message = _validate_squad_config()
    if not config_ok:
        return JsonResponse({"error": config_message}, status=400)

    organization = get_request_organization(request)
    plan = get_object_or_404(Plan, id=plan_id)

    # Get coupon from request if provided
    coupon = None
    final_amount = Decimal(str(plan.price))
    coupon_code = request.GET.get('coupon_code') or request.POST.get('coupon_code')
    
    if coupon_code:
        success, final_amount, message, coupon = apply_coupon(coupon_code, organization, plan)
        if not success:
            return JsonResponse({"error": message}, status=400)

    amount_minor = int(final_amount * 100)
    reference = str(uuid.uuid4())

    # create inactive subscription first
    subscription = Subscription.objects.create(
        organization=organization,
        plan=plan,
        provider="squadco",
        currency="NGN",
        start_date=timezone.now(),
        end_date=timezone.now() + timezone.timedelta(days=plan.duration_in_days),
        is_active=False,
    )

    # create pending payment
    payment = Payment.objects.create(
        subscription=subscription,
        amount=final_amount,
        payment_method="squadco",
        transaction_id=reference,
        payment_status="pending",
        coupon=coupon,
    )
    
    # Record coupon redemption if coupon was used
    if coupon:
        CouponRedemption.objects.create(
            coupon=coupon,
            organization=organization,
            subscription=subscription,
        )
        coupon.uses += 1
        coupon.save()

    data = {
        "email": request.user.email,
        "amount": amount_minor,
        "currency": "NGN",
        "transaction_ref": reference,
        "callback_url": request.build_absolute_uri(reverse("verify_payment")),
    }
    resp = requests.post(
        f"{settings.SQUAD_API_BASE_URL}/transaction/initiate",
        headers=_squad_headers(),
        json=data,
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        return JsonResponse({"error": "Unable to initialize payment"}, status=400)

    response_data = resp.json()
    checkout_url = _extract_checkout_url(response_data)
    if not checkout_url:
        return JsonResponse({"error": "Payment initialized but no checkout URL returned"}, status=400)

    return JsonResponse({
        "reference": reference,
        "checkout_url": checkout_url,
    })



@csrf_exempt
@login_required
def create_payment(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    config_ok, config_message = _validate_squad_config()
    if not config_ok:
        return JsonResponse({"error": config_message}, status=400)
    
    try:
        data = json.loads(request.body)
        reference = data.get("reference")
        print(f"📝 Creating payment with reference: {reference}")
        
        # Support both old plan_id format and new tier/size/frequency format
        if "plan_id" in data:
            plan = get_object_or_404(Plan, id=data["plan_id"])
        else:
            # New format: tier, size, billing_frequency
            tier = data.get("tier")
            size = data.get("size")
            frequency = data.get("frequency")
            if not all([tier, size, frequency]):
                print(f"❌ Missing plan parameters: tier={tier}, size={size}, frequency={frequency}")
                return JsonResponse({"error": "Missing plan parameters"}, status=400)
            plan = get_or_create_plan(tier, size, frequency)
            print(f"✓ Plan retrieved: {plan.tier} {plan.size} {plan.billing_frequency} - ₦{plan.price}")
        
        amount = data.get("amount", float(plan.price))
        coupon_code = data.get("coupon_code", "")
        is_free = data.get("is_free", False)
        org = get_request_organization(request)

        coupon = None
        
        # Handle coupon if provided
        if coupon_code:
            try:
                coupon = Coupon.objects.get(code__iexact=coupon_code)
                if not coupon.is_valid():
                    print(f"❌ Coupon expired: {coupon_code}")
                    return JsonResponse({"error": "Coupon is no longer valid"}, status=400)
                if CouponRedemption.objects.filter(coupon=coupon, organization=org).exists():
                    print(f"❌ Coupon already used: {coupon_code}")
                    return JsonResponse({"error": "Coupon already used"}, status=400)
                print(f"✓ Coupon valid: {coupon_code}")
            except Coupon.DoesNotExist:
                print(f"❌ Coupon not found: {coupon_code}")
                return JsonResponse({"error": "Invalid coupon code"}, status=400)
        
        # Check for an existing pending payment for this org + plan to avoid
        # creating duplicate Squad transactions (Squad rejects if one is already pending).
        # Use select_for_update inside atomic() to prevent two simultaneous requests
        # both passing this check and creating duplicate transactions.
        with transaction.atomic():
            existing_payment = (
                Payment.objects
                .select_for_update()
                .filter(
                    subscription__organization=org,
                    subscription__plan=plan,
                    payment_status="pending",
                    payment_method="squadco",
                )
                .select_related("subscription")
                .order_by("-created_at")
                .first()
            )
            if existing_payment and existing_payment.transaction_id:
                # Before reusing this reference, check with Squad whether it was already paid.
                # This catches the case where verify_payment was interrupted (e.g. by a login
                # redirect) so our DB still shows "pending" but Squad already processed the payment.
                # It also catches stale references from a different environment (live vs sandbox).
                squad_knows_ref = False
                already_paid = False
                try:
                    squad_verify = requests.get(
                        f"{settings.SQUAD_API_BASE_URL}/transaction/verify/{existing_payment.transaction_id}",
                        headers=_squad_headers(),
                        timeout=(5, 10),
                    )
                    if squad_verify.status_code == 200:
                        squad_knows_ref = True
                        verify_status = _extract_status(squad_verify.json())
                        if verify_status in {'success', 'successful', 'completed', 'paid'}:
                            already_paid = True
                except requests.exceptions.RequestException:
                    pass  # Network error — fall through to discard and recreate

                if already_paid:
                    # Squad processed it but our DB missed it — activate now
                    print(f"⚠️ Stale pending payment detected (Squad already processed): {existing_payment.transaction_id}")
                    subscription = existing_payment.subscription
                    existing_payment.payment_status = 'completed'
                    existing_payment.save()
                    subscription.is_active = True
                    subscription.save()
                    Subscription.objects.filter(
                        organization=subscription.organization,
                        is_active=True,
                    ).exclude(id=subscription.id).update(is_active=False)
                    if subscription.end_date > timezone.now():
                        deactivate_subscription.apply_async(
                            args=[str(subscription.id)],
                            eta=subscription.end_date,
                        )
                    owner = subscription.organization.owned_by
                    if owner and owner.email:
                        task_send_subscription_success_email.delay(
                            owner.id, subscription.organization.id, subscription.id
                        )
                    return JsonResponse({"success": True, "message": "Subscription activated!"})

                if not squad_knows_ref:
                    # Squad doesn't recognise this reference — was created with different keys
                    # (e.g. live vs sandbox switch) or expired. Void it and create a fresh one.
                    print(f"⚠️ Squad does not recognise reference {existing_payment.transaction_id} — voiding and recreating")
                    existing_payment.payment_status = 'failed'
                    existing_payment.save()
                    existing_payment.subscription.delete()
                    # Fall through to create a new transaction below

                else:
                    # Squad knows the ref and it's still pending — safe to reuse
                    existing_checkout_url = _infer_checkout_url(existing_payment.transaction_id)
                    print(f"Reusing existing pending payment: {existing_payment.transaction_id}")
                    return JsonResponse({
                        "status": "ok",
                        "reference": existing_payment.transaction_id,
                        "amount": str(existing_payment.amount),
                        "currency": "NGN",
                        "checkout_url": existing_checkout_url,
                    })

        # NOTE: Do NOT deactivate existing subscriptions here.
        # Only deactivate them after payment is confirmed in verify_payment.
        subscription = Subscription.objects.create(
            organization=org,
            plan=plan,
            provider="squadco",
            currency="NGN",
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=plan.duration_in_days),
            is_active=False,
        )
        print(f"✓ Subscription created: {subscription.id} (expires {subscription.end_date})")

        # For free month coupons, activate immediately without payment
        if is_free and coupon and coupon.type == 'free_month':
            # Record redemption
            CouponRedemption.objects.create(
                coupon=coupon,
                organization=org,
                subscription=subscription,
            )
            coupon.uses += 1
            coupon.save()
            
            # Create completed payment record
            Payment.objects.create(
                subscription=subscription,
                amount=Decimal('0.00'),
                payment_method="free_coupon",
                transaction_id=f"free_coupon_{subscription.id}",
                payment_status="completed",
                coupon=coupon,
            )
            
            # Activate subscription immediately
            subscription.is_active = True
            subscription.save()
            
            # Schedule deactivation task
            if subscription.end_date > timezone.now():
                deactivate_subscription.apply_async(
                    args=[str(subscription.id)],
                    eta=subscription.end_date
                )
            
            # Queue confirmation email — never blocks the request
            owner = subscription.organization.owned_by
            if owner and owner.email:
                task_send_subscription_success_email.delay(
                    owner.id, subscription.organization.id, subscription.id
                )

            # Surface success to UI via Django messages (shown as toast on next page)
            try:
                messages.success(request, "Subscription activated! Free month coupon applied.")
            except Exception:
                pass

            print(f"✓ Free month subscription activated immediately")
            return JsonResponse({"success": True, "message": "Subscription activated with free month coupon!"})
        
        # For paid plans, register the transaction with Squad first so the widget can load it.
        transaction_reference = reference or uuid.uuid4().hex

        squad_payload = {
            "email": request.user.email,
            "amount": int(float(amount) * 100),  # kobo
            "currency": "NGN",
            "initiate_type": "inline",
            "transaction_ref": transaction_reference,
            "callback_url": request.build_absolute_uri(reverse("verify_payment")),
            "payment_channels": ["card", "bank", "ussd", "transfer"],
        }
        print(f"📡 Registering transaction with Squad: ref={transaction_reference} amount={squad_payload['amount']}")

        squad_resp = None
        last_request_error = None
        max_attempts = 2
        api_bases = _squad_api_bases()

        for attempt in range(1, max_attempts + 1):
            for api_base in api_bases:
                try:
                    squad_resp = requests.post(
                        f"{api_base}/transaction/initiate",
                        headers=_squad_headers(),
                        json=squad_payload,
                        timeout=(8, 25),
                    )
                    print(f"📡 Squad initiate reachable via {api_base}")
                    break
                except requests.exceptions.Timeout as timeout_err:
                    last_request_error = timeout_err
                    print(
                        f"⚠️ Squad /transaction/initiate timeout on {api_base} "
                        f"(attempt {attempt}/{max_attempts})"
                    )
                except requests.exceptions.RequestException as req_err:
                    last_request_error = req_err
                    print(
                        f"⚠️ Squad request error on {api_base} "
                        f"(attempt {attempt}/{max_attempts}): {req_err}"
                    )

            if squad_resp is not None:
                break

            if attempt < max_attempts:
                time.sleep(1.5 * attempt)

        squad_data_payload = {}

        if squad_resp is None:
            print(f"⚠️ Squad /transaction/initiate failed after {max_attempts} attempts: {last_request_error}")

            # Recovery path: if initiate timed out but Squad still created the transaction,
            # verify by reference and continue without forcing the user to retry manually.
            try:
                verify_resp = None
                for api_base in api_bases:
                    try:
                        verify_resp = requests.get(
                            f"{api_base}/transaction/verify/{transaction_reference}",
                            headers=_squad_headers(),
                            timeout=(8, 15),
                        )
                        if verify_resp.status_code == 200:
                            break
                    except requests.exceptions.RequestException as verify_call_err:
                        print(f"⚠️ Verify timeout/error on {api_base}: {verify_call_err}")

                if verify_resp is not None and verify_resp.status_code == 200:
                    verify_data = verify_resp.json()
                    verify_payload = verify_data.get("data") or {}
                    if verify_payload.get("transaction_ref"):
                        inferred_url = _infer_checkout_url(verify_payload.get("transaction_ref"))
                        verify_payload.setdefault("checkout_url", inferred_url)
                        squad_data_payload = verify_payload
                        print(
                            f"⚠️ Recovered transaction after timeout via verify endpoint: {verify_payload.get('transaction_ref')}"
                        )
                    else:
                        return JsonResponse({"error": "Payment provider timed out. Please try again."}, status=503)
                else:
                    return JsonResponse({"error": "Payment provider timed out. Please try again."}, status=503)
            except requests.exceptions.RequestException as verify_err:
                print(f"❌ Timeout recovery verify failed: {verify_err}")
                return JsonResponse({"error": "Payment provider timed out. Please try again."}, status=503)
        else:
            print(f"📡 Squad initiate response: {squad_resp.status_code} {squad_resp.text[:300]}")

            if squad_resp.status_code not in (200, 201):
                err_text = squad_resp.text[:300] if squad_resp.text else "(no body)"
                return JsonResponse({"error": f"Unable to initialize payment: {err_text}"}, status=400)

            squad_data = squad_resp.json()
            # Squad may return a transaction_ref in data — use it; fall back to ours.
            squad_data_payload = squad_data.get("data") or {}

        confirmed_ref = squad_data_payload.get("transaction_ref") or transaction_reference
        checkout_url = _extract_checkout_url({"data": squad_data_payload})

        if not checkout_url and confirmed_ref:
            checkout_url = _infer_checkout_url(confirmed_ref)

        if not checkout_url:
            response_snippet = squad_resp.text[:300] if squad_resp is not None else str(squad_data_payload)[:300]
            print(f"❌ Squad initiate returned no checkout_url: {response_snippet}")
            return JsonResponse({"error": "Squad did not return checkout URL"}, status=400)

        print(f"✓ Squad transaction registered, ref: {confirmed_ref}")

        payment = Payment.objects.create(
            subscription=subscription,
            amount=amount,
            payment_method="squadco",
            transaction_id=confirmed_ref,
            payment_status="pending",
            coupon=coupon,
        )

        # Record coupon redemption after payment
        if coupon:
            CouponRedemption.objects.create(
                coupon=coupon,
                organization=org,
                subscription=subscription,
            )
            coupon.uses += 1
            coupon.save()

        print(f"✓ Payment record created: {payment.id} (amount: ₦{amount}, reference: {confirmed_ref})")
        return JsonResponse({
            "status": "ok",
            "reference": confirmed_ref,
            "amount": str(amount),
            "currency": "NGN",
            "checkout_url": checkout_url,
        })
    
    except Exception as e:
        print(f"❌ Error in create_payment: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)




def verify_payment(request):
    reference = (
        request.GET.get('reference')
        or request.GET.get('transaction_ref')
        or request.GET.get('transaction_reference')
        or request.GET.get('trx_ref')
    )

    def _safe_redirect():
        """Redirect to settings if logged in, otherwise to login with next=settings."""
        from django.urls import reverse as _reverse
        if request.user.is_authenticated:
            return redirect('settings')
        return redirect(f"{_reverse('login')}?next={_reverse('settings')}")

    if not reference:
        print(f" No reference provided")
        messages.error(request, 'Invalid payment reference')
        return _safe_redirect()
    
    try:
        print(f"🔍 Verifying payment with reference: {reference}")

        # Verify payment with SquadCo
        try:
            response = requests.get(
                f"{settings.SQUAD_API_BASE_URL}/transaction/verify/{reference}",
                headers=_squad_headers(),
                timeout=(8, 25),
            )
        except requests.exceptions.Timeout:
            print(f"⚠️ Timeout verifying payment {reference} — existing subscription preserved")
            messages.warning(
                request,
                "Payment verification timed out. Your current subscription is unchanged. "
                "If you were charged, please contact support with reference: " + reference
            )
            return _safe_redirect()
        except requests.exceptions.RequestException as net_err:
            print(f"⚠️ Network error verifying payment {reference}: {net_err}")
            messages.warning(
                request,
                "Could not reach payment provider. Your current subscription is unchanged. "
                "Please try again or contact support with reference: " + reference
            )
            return _safe_redirect()

        print(f"📡 SquadCo response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            status = _extract_status(data)
            print(f"✅ SquadCo data: {status}")
            
            if status in {'success', 'successful', 'completed', 'paid'}:
                # Use select_for_update inside atomic() to prevent two simultaneous
                # verify_payment calls from double-activating the subscription.
                with transaction.atomic():
                    try:
                        payment = Payment.objects.select_for_update().get(transaction_id=reference)
                        print(f"💳 Found payment record: {payment.id}")
                    except Payment.DoesNotExist:
                        print(f"❌ Payment not found for reference: {reference}")
                        messages.error(request, 'Payment record not found')
                        return _safe_redirect()

                    if payment.payment_status != 'completed':
                        payment.payment_status = 'completed'
                        payment.save()
                        print(f"✓ Payment marked as completed")
                        
                        # Activate the new subscription
                        subscription = payment.subscription
                        subscription.is_active = True
                        subscription.save()
                        print(f"✓ Subscription activated: {subscription.id}")

                        # NOW deactivate all other active subscriptions for this org
                        old_subs = Subscription.objects.filter(
                            organization=subscription.organization,
                            is_active=True,
                        ).exclude(id=subscription.id)
                        count = old_subs.count()
                        if count > 0:
                            old_subs.update(is_active=False)
                            print(f"✓ Deactivated {count} previous subscription(s)")
                        
                        # Schedule deactivation task using Celery
                        if subscription.end_date > timezone.now():
                            deactivate_subscription.apply_async(
                                args=[str(subscription.id)],
                                eta=subscription.end_date
                            )
                            print(f"✓ Deactivation scheduled for: {subscription.end_date}")
                        
                        # Queue confirmation email — never blocks the payment redirect
                        owner = subscription.organization.owned_by
                        if owner and owner.email:
                            task_send_subscription_success_email.delay(
                                owner.id, subscription.organization.id, subscription.id
                            )
                            print(f"✓ Subscription email queued for: {owner.email}")
                        
                        messages.success(request, 'Payment successful! Your subscription is now active.')
                    else:
                        print(f"ℹ️ Payment already processed")
                        messages.info(request, 'This payment has already been processed.')
                return _safe_redirect()
            else:
                print(f"❌ Payment status not successful: {status}")
                messages.error(request, 'Payment verification failed')
                return _safe_redirect()
        else:
            print(f"❌ SquadCo API error: {response.status_code}")
            print(f"Response: {response.text}")
            messages.error(request, 'Could not verify payment')
            return _safe_redirect()
            
    except Exception as e:
        print(f"❌ Unexpected error during payment verification: {str(e)}")
        import traceback
        traceback.print_exc()
        messages.error(request, f'An error occurred: {str(e)}')
        return _safe_redirect()

# @login_required
# def verify_payment(request):
#     reference = request.GET.get("reference")
#     headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}

#     resp = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers=headers).json()

#     try:
#         with transaction.atomic():
#             payment = Payment.objects.select_for_update().get(transaction_id=reference)

#             if resp["data"]["status"] == "success" and payment.payment_status != "completed":
#                 payment.payment_status = "completed"
#                 payment.save()

#                 subscription = payment.subscription
#                 subscription.is_active = True
#                 subscription.save()
#                 deactivate_subscription.configure(
#                     schedule_at=subscription.end_date
#                 ).defer(
#                     subscription_id=str(subscription.id)
#                 )
#                 messages.success(request, "Payment successful! Your subscription is now active.")
#                 return redirect("settings")
#             elif resp["data"]["status"] != "success":
#                 payment.payment_status = "failed"
#                 payment.save()
#     except Payment.DoesNotExist:
#         return HttpResponse("Payment not found", status=404)

#     return redirect("settings")



@csrf_exempt
def squadco_webhook(request):
    print("🔥 Webhook endpoint hit")
    print("Headers:", request.headers)
    print("Body:", request.body)
    
    payload = request.body
    print("🔔 Raw webhook payload:", payload)
    signature = (
        request.headers.get("X-Squad-Signature")
        or request.headers.get("X-Squadco-Signature")
        or request.headers.get("X-Paystack-Signature")
    )

    import hmac, hashlib
    expected = hmac.new(
        settings.SQUAD_SECRET_KEY.encode("utf-8"),
        payload,
        hashlib.sha512
    ).hexdigest()

    if signature != expected:
        return HttpResponse(status=401)

    event = json.loads(payload.decode("utf-8"))
    print("✅ Parsed event:", event) 

    event_name = str(event.get("event") or event.get("type") or "").lower()
    status = _extract_status(event)

    if event_name in {"charge.success", "transaction.success", "payment.success"} or status in {"success", "successful", "completed", "paid"}:
        data = event.get("data", {}) if isinstance(event, dict) else {}
        reference = (
            data.get("reference")
            or data.get("transaction_ref")
            or data.get("transaction_reference")
            or data.get("trx_ref")
        )
        if not reference:
            return HttpResponse(status=200)

        with transaction.atomic():
            try:
                payment = Payment.objects.select_for_update().get(transaction_id=reference)
                if payment.payment_status != "completed":
                    payment.payment_status = "completed"
                    payment.save()

                    subscription = payment.subscription
                    subscription.is_active = True
                    subscription.save()
                    
                    # Schedule deactivation task
                    if subscription.end_date > timezone.now():
                        deactivate_subscription.apply_async(
                            args=[str(subscription.id)],
                            eta=subscription.end_date
                        )
                    
                    # Queue subscription success email
                    owner = subscription.organization.owned_by
                    if owner and owner.email:
                        task_send_subscription_success_email.delay(
                            owner.id, subscription.organization.id, subscription.id
                        )
            except Payment.DoesNotExist:
                pass

    return HttpResponse(status=200)