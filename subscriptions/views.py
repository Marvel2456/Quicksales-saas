from django.shortcuts import render, redirect, HttpResponse
from account.models import Organization
from .models import Subscription, Plan, Payment
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


# Create your views here.



@role_required(roles=['owner'])
@login_required
def settingsView(request):
    organization = request.user.organization
    subscription = Subscription.objects.filter(organization=organization, is_active=True).order_by('-end_date').first()
    plans = Plan.objects.all().exclude(name='Free').order_by('price')

    context = {
        'organization': organization,
        'subscription': subscription,
        'plans': plans
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
    subscription = get_object_or_404(
        Subscription,
        id=subscription_id,
        organization=request.user.organization,
        is_active=True
    )

    subscription.is_active = False
    subscription.save()

    messages.success(request, "Your subscription has been cancelled successfully.")
    return redirect("settings")


@login_required
def init_payment(request, plan_id):
    organization = request.user.organization
    plan = get_object_or_404(Plan, id=plan_id)

    amount = int(plan.price * 100)  # Paystack expects kobo
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
    Payment.objects.create(
        subscription=subscription,
        amount=plan.price,
        payment_method="paystack",
        transaction_id=reference,
        payment_status="pending",
    )

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
    data = json.loads(request.body)
    reference = data["reference"]
    plan_id = data["plan_id"]
    amount = data["amount"]

    plan = get_object_or_404(Plan, id=plan_id)
    subscription = Subscription.objects.create(
        organization=request.user.organization,
        plan=plan,
        provider="paystack",
        currency="NGN",
        start_date=timezone.now(),
        end_date=timezone.now() + timezone.timedelta(days=plan.duration_in_days),
        is_active=False,
    )

    Payment.objects.create(
        subscription=subscription,
        amount=amount,
        payment_method="paystack",
        transaction_id=reference,
        payment_status="pending",
    )
    print("Payment record created")

    return JsonResponse({"status": "ok"})




@login_required
def verify_payment(request):
    reference = request.GET.get('reference')
    
    if not reference:
        messages.error(request, 'Invalid payment reference')
        return redirect('settings')
    
    try:
        # Verify payment with Paystack
        headers = {
            'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        }
        response = requests.get(
            f'https://api.paystack.co/transaction/verify/{reference}',
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data['data']['status'] == 'success':
                # Get the payment record using transaction_id (not reference)
                with transaction.atomic():
                    payment = Payment.objects.select_for_update().get(transaction_id=reference)
                    
                    # Only update if not already completed
                    if payment.payment_status != 'completed':
                        payment.payment_status = 'completed'
                        payment.save()
                        
                        # Activate subscription
                        subscription = payment.subscription
                        subscription.is_active = True
                        subscription.save()
                        
                        # Schedule deactivation task using Celery
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
                            # Log but don't fail the payment if email fails
                            print(f"Failed to send subscription email: {email_error}")
                        
                        messages.success(request, 'Payment successful! Your subscription is now active.')
                    else:
                        messages.info(request, 'This payment has already been processed.')
                        
                return redirect('settings')
            else:
                messages.error(request, 'Payment verification failed')
                return redirect('settings')
        else:
            messages.error(request, 'Could not verify payment')
            return redirect('settings')
            
    except Payment.DoesNotExist:
        messages.error(request, 'Payment record not found')
        return redirect('settings')
    except Exception as e:
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