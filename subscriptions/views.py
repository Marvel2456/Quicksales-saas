from django.shortcuts import render, redirect, HttpResponse
from account.models import Organization
from .models import Subscription, Plan, Payment, Coupon, CouponRedemption
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from account.decorators import role_required
from django.shortcuts import get_object_or_404
import requests
from django.conf import settings
from django.urls import reverse
from django.http import JsonResponse
import uuid
import json
from django.utils import timezone
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from account.tasks import deactivate_subscription
from account.emails import send_subscription_success_email
from decimal import Decimal


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
    # Check if user has owner role
    if request.user.role != 'owner':
        messages.error(request, "Only organization owners can access settings.")
        return redirect('dashboard')
    
    # Check if user has an organization
    if not hasattr(request.user, 'organization') or request.user.organization is None:
        messages.error(request, "You must be part of an organization to access settings.")
        return redirect('dashboard')
    
    organization = request.user.organization
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
    if request.user.role != 'owner':
        messages.error(request, "Only organization owners can cancel subscriptions.")
        return redirect("settings")
    
    # Get the subscription
    try:
        subscription = Subscription.objects.get(
            id=subscription_id,
            organization=request.user.organization,
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
    organization = request.user.organization
    plan = get_object_or_404(Plan, id=plan_id)

    # Get coupon from request if provided
    coupon = None
    final_amount = Decimal(str(plan.price))
    coupon_code = request.GET.get('coupon_code') or request.POST.get('coupon_code')
    
    if coupon_code:
        success, final_amount, message, coupon = apply_coupon(coupon_code, organization, plan)
        if not success:
            return JsonResponse({"error": message}, status=400)

    amount = int(final_amount * 100)  # Paystack expects kobo
    reference = str(uuid.uuid4())

    # create inactive subscription first
    subscription = Subscription.objects.create(
        organization=organization,
        plan=plan,
        provider="paystack",
        currency="NGN",
        start_date=timezone.now(),
        end_date=timezone.now() + timezone.timedelta(days=plan.duration_in_days),
        is_active=False,
    )

    # create pending payment
    payment = Payment.objects.create(
        subscription=subscription,
        amount=final_amount,
        payment_method="paystack",
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

    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
    data = {
        "email": request.user.email,
        "amount": amount,
        "reference": reference,
        "callback_url": request.build_absolute_uri(reverse("verify_payment")),
    }
    resp = requests.post("https://api.paystack.co/transaction/initialize", headers=headers, json=data)

    if resp.status_code != 200:
        return JsonResponse({"error": "Unable to initialize payment"}, status=400)

    return JsonResponse(resp.json()["data"])  # contains `authorization_url`



@csrf_exempt
@login_required
def create_payment(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
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

        coupon = None
        
        # Handle coupon if provided
        if coupon_code:
            try:
                coupon = Coupon.objects.get(code__iexact=coupon_code)
                if not coupon.is_valid():
                    print(f"❌ Coupon expired: {coupon_code}")
                    return JsonResponse({"error": "Coupon is no longer valid"}, status=400)
                if CouponRedemption.objects.filter(coupon=coupon, organization=request.user.organization).exists():
                    print(f"❌ Coupon already used: {coupon_code}")
                    return JsonResponse({"error": "Coupon already used"}, status=400)
                print(f"✓ Coupon valid: {coupon_code}")
            except Coupon.DoesNotExist:
                print(f"❌ Coupon not found: {coupon_code}")
                return JsonResponse({"error": "Invalid coupon code"}, status=400)
        
        # Deactivate previous subscriptions for this organization
        old_subs = Subscription.objects.filter(
            organization=request.user.organization,
            is_active=True
        )
        count = old_subs.count()
        if count > 0:
            old_subs.update(is_active=False)
            print(f"✓ Deactivated {count} previous subscription(s)")
        
        subscription = Subscription.objects.create(
            organization=request.user.organization,
            plan=plan,
            provider="paystack",
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
                organization=request.user.organization,
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
            
            # Send email
            try:
                owner = subscription.organization.owned_by
                if owner and owner.email:
                    send_subscription_success_email(owner, subscription.organization, subscription)
            except Exception as email_error:
                print(f"Email error: {email_error}")

            # Surface success to UI via Django messages (shown as toast on next page)
            try:
                messages.success(request, "Subscription activated! Free month coupon applied.")
            except Exception:
                pass

            print(f"✓ Free month subscription activated immediately")
            return JsonResponse({"success": True, "message": "Subscription activated with free month coupon!"})
        
        # For paid plans, create pending payment
        payment = Payment.objects.create(
            subscription=subscription,
            amount=amount,
            payment_method="paystack",
            transaction_id=reference or f"pending_{subscription.id}",
            payment_status="pending",
            coupon=coupon,
        )
        
        # Record coupon redemption after payment
        if coupon:
            CouponRedemption.objects.create(
                coupon=coupon,
                organization=request.user.organization,
                subscription=subscription,
            )
            coupon.uses += 1
            coupon.save()
        
        print(f"✓ Payment record created: {payment.id} (amount: ₦{amount}, reference: {reference})")

        return JsonResponse({"status": "ok"})
    
    except Exception as e:
        print(f"❌ Error in create_payment: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)




@login_required
def verify_payment(request):
    reference = request.GET.get('reference')
    
    if not reference:
        print(f" No reference provided")
        messages.error(request, 'Invalid payment reference')
        return redirect('settings')
    
    try:
        print(f"🔍 Verifying payment with reference: {reference}")
        print(f"👤 Organization: {request.user.organization.name}")
        
        # Verify payment with Paystack
        headers = {
            'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        }
        response = requests.get(
            f'https://api.paystack.co/transaction/verify/{reference}',
            headers=headers
        )
        
        print(f"📡 Paystack response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Paystack data: {data.get('data', {}).get('status')}")
            
            if data['data']['status'] == 'success':
                # Get the payment record using transaction_id (not reference)
                try:
                    payment = Payment.objects.get(transaction_id=reference)
                    print(f"💳 Found payment record: {payment.id}")
                except Payment.DoesNotExist:
                    print(f"❌ Payment not found for reference: {reference}")
                    print(f"Available transactions: {list(Payment.objects.filter(subscription__organization=request.user.organization).values_list('transaction_id', flat=True))}")
                    messages.error(request, 'Payment record not found')
                    return redirect('settings')
                
                # Only update if not already completed
                if payment.payment_status != 'completed':
                    with transaction.atomic():
                        payment.payment_status = 'completed'
                        payment.save()
                        print(f"✓ Payment marked as completed")
                        
                        # Activate subscription
                        subscription = payment.subscription
                        subscription.is_active = True
                        subscription.save()
                        print(f"✓ Subscription activated: {subscription.id}")
                        
                        # Schedule deactivation task using Celery
                        if subscription.end_date > timezone.now():
                            deactivate_subscription.apply_async(
                                args=[str(subscription.id)],
                                eta=subscription.end_date
                            )
                            print(f"✓ Deactivation scheduled for: {subscription.end_date}")
                        
                        # Send subscription success email
                        try:
                            owner = subscription.organization.owned_by
                            if owner and owner.email:
                                send_subscription_success_email(owner, subscription.organization, subscription)
                                print(f"✓ Email sent to: {owner.email}")
                        except Exception as email_error:
                            # Log but don't fail the payment if email fails
                            print(f"⚠️ Failed to send subscription email: {email_error}")
                        
                        messages.success(request, 'Payment successful! Your subscription is now active.')
                else:
                    print(f"ℹ️ Payment already processed")
                    messages.info(request, 'This payment has already been processed.')
                    
                return redirect('settings')
            else:
                print(f"❌ Payment status not success: {data['data']['status']}")
                messages.error(request, 'Payment verification failed')
                return redirect('settings')
        else:
            print(f"❌ Paystack API error: {response.status_code}")
            print(f"Response: {response.text}")
            messages.error(request, 'Could not verify payment')
            return redirect('settings')
            
    except Exception as e:
        print(f"❌ Unexpected error during payment verification: {str(e)}")
        import traceback
        traceback.print_exc()
        messages.error(request, f'An error occurred: {str(e)}')
        return redirect('settings')

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
def paystack_webhook(request):
    print("🔥 Webhook endpoint hit")
    print("Headers:", request.headers)
    print("Body:", request.body)
    
    payload = request.body
    print("🔔 Raw webhook payload:", payload)
    signature = request.headers.get("X-Paystack-Signature")

    import hmac, hashlib
    expected = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode("utf-8"),
        payload,
        hashlib.sha512
    ).hexdigest()

    if signature != expected:
        return HttpResponse(status=401)

    event = json.loads(payload.decode("utf-8"))
    print("✅ Parsed event:", event) 

    if event["event"] == "charge.success":
        reference = event["data"]["reference"]

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
                    
                    # Send subscription success email
                    try:
                        owner = subscription.organization.owned_by
                        if owner and owner.email:
                            send_subscription_success_email(owner, subscription.organization, subscription)
                    except Exception as email_error:
                        print(f"Webhook email failed: {email_error}")
            except Payment.DoesNotExist:
                pass

    return HttpResponse(status=200)