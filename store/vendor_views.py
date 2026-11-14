import csv
import secrets
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction, models
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.urls import reverse

from account.decorators import role_required
from account.utils import get_request_organization
from account.models import Branch, Organization
from ims.models import Inventory, Sale, SalesItem, Product
from .models import (
    StoreListing, ProductListing, OnlineOrder, OnlineOrderItem,
    StoreDiscount, StoreDiscountRedemption, StoreBankAccount, StorePayout,
    ServiceListing, ServiceEnrollment
)
from .emails import send_service_enrollment_email
from .decorators import require_online_store_access
from subscriptions.services.gateways import (
    BachsGateway,
    get_active_gateway_name,
    validate_positive_amount,
)


import logging
import json
import requests
from decouple import config
from django.conf import settings

logger = logging.getLogger(__name__)

# Standard NIP & Paystack Bank Codes for Nigerian Financial Institutions
NIGERIAN_BANKS = {
    "000013": {"name": "Guaranty Trust Bank (GTBank)", "squad_code": "000013", "paystack_code": "058"},
    "000014": {"name": "Access Bank", "squad_code": "000014", "paystack_code": "044"},
    "000015": {"name": "Zenith Bank", "squad_code": "000015", "paystack_code": "057"},
    "000016": {"name": "First Bank of Nigeria", "squad_code": "000016", "paystack_code": "011"},
    "000004": {"name": "United Bank for Africa (UBA)", "squad_code": "000004", "paystack_code": "033"},
    "100004": {"name": "OPay Digital Services", "squad_code": "100004", "paystack_code": "999992"},
    "100033": {"name": "PalmPay", "squad_code": "100033", "paystack_code": "999991"},
    "090267": {"name": "Kuda Microfinance Bank", "squad_code": "090267", "paystack_code": "50211"},
    "090405": {"name": "Moniepoint Microfinance Bank", "squad_code": "090405", "paystack_code": "50515"},
    "000007": {"name": "Fidelity Bank", "squad_code": "000007", "paystack_code": "070"},
    "000003": {"name": "First City Monument Bank (FCMB)", "squad_code": "000003", "paystack_code": "214"},
    "000012": {"name": "Stanbic IBTC Bank", "squad_code": "000012", "paystack_code": "221"},
    "000001": {"name": "Sterling Bank", "squad_code": "000001", "paystack_code": "232"},
    "000018": {"name": "Union Bank of Nigeria", "squad_code": "000018", "paystack_code": "032"},
    "000017": {"name": "Wema Bank (ALAT)", "squad_code": "000017", "paystack_code": "035"},
    "000002": {"name": "Keystone Bank", "squad_code": "000002", "paystack_code": "082"},
    "000008": {"name": "Polaris Bank", "squad_code": "000008", "paystack_code": "076"},
    "000023": {"name": "Providus Bank", "squad_code": "000023", "paystack_code": "101"},
    "000026": {"name": "Taj Bank", "squad_code": "000026", "paystack_code": "302"},
    "000006": {"name": "Jaiz Bank", "squad_code": "000006", "paystack_code": "301"},
    "090328": {"name": "FairMoney Microfinance Bank", "squad_code": "090328", "paystack_code": "51318"},
}


@login_required
@role_required(['owner', 'manager'])
@require_online_store_access
def verify_bank_account_api(request):
    """
    Verify account number and return resolved account holder name.
    Hybrid resolver: SquadCo Account Lookup API with Paystack resolve fallback.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        body = request.POST

    account_number = str(body.get('account_number', '')).strip()
    bank_code = str(body.get('bank_code', '')).strip()
    bank_name = str(body.get('bank_name', '')).strip()

    if not account_number or len(account_number) != 10 or not account_number.isdigit():
        return JsonResponse({'success': False, 'message': 'Account number must be exactly 10 digits.'}, status=400)

    # Resolve bank metadata
    bank_info = NIGERIAN_BANKS.get(bank_code)
    if not bank_info:
        for code, info in NIGERIAN_BANKS.items():
            if info['name'].lower() == bank_name.lower() or info.get('paystack_code') == bank_code:
                bank_info = info
                bank_code = code
                break

    resolved_account_name = None

    # 1. Try SquadCo Account Lookup API
    if settings.SQUAD_SECRET_KEY and settings.SQUAD_API_BASE_URL and bank_code:
        try:
            squad_headers = {
                "Authorization": f"Bearer {settings.SQUAD_SECRET_KEY}",
                "Content-Type": "application/json",
            }
            if settings.SQUAD_MERCHANT_ID:
                squad_headers["MerchantId"] = settings.SQUAD_MERCHANT_ID

            squad_payload = {
                "bank_code": bank_code,
                "account_number": account_number,
            }
            resp = requests.post(
                f"{settings.SQUAD_API_BASE_URL.rstrip('/')}/payout/account/lookup",
                headers=squad_headers,
                json=squad_payload,
                timeout=12
            )
            if resp.status_code == 200:
                resp_data = resp.json()
                data_obj = resp_data.get('data') or {}
                name = data_obj.get('account_name')
                if name:
                    resolved_account_name = name.strip()
        except Exception as e:
            logger.debug("Squad account lookup exception: %s", e)

    # 2. Fallback to Paystack Bank Resolve API
    paystack_sk = config('PAYSTACK_SECRET_KEY', default='').strip() or getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    if not resolved_account_name and paystack_sk and bank_info and bank_info.get('paystack_code'):
        try:
            pst_code = bank_info['paystack_code']
            pst_resp = requests.get(
                f"https://api.paystack.co/bank/resolve?account_number={account_number}&bank_code={pst_code}",
                headers={"Authorization": f"Bearer {paystack_sk}"},
                timeout=12
            )
            if pst_resp.status_code == 200:
                pst_data = pst_resp.json()
                name = pst_data.get('data', {}).get('account_name')
                if name:
                    resolved_account_name = name.strip()
        except Exception as e:
            logger.debug("Paystack account lookup fallback exception: %s", e)

    if resolved_account_name:
        return JsonResponse({
            'success': True,
            'account_name': resolved_account_name,
            'account_number': account_number,
            'bank_name': bank_info['name'] if bank_info else bank_name,
            'bank_code': bank_code,
        })
    else:
        return JsonResponse({
            'success': False,
            'message': f"Could not verify account name for {account_number}. Please check that the bank and account number are correct."
        }, status=400)


@login_required
@role_required(['owner', 'manager'])
@require_online_store_access
def store_settings(request):
    """
    Vendor store settings (store status, tagline, banner, social links, default branch).
    """
    org = get_request_organization(request)
    store, _ = StoreListing.objects.get_or_create(organization=org)
    branches = Branch.objects.filter(organization=org)

    if request.method == 'POST':
        is_active = request.POST.get('is_active') == 'on'
        tagline = request.POST.get('tagline', '').strip()
        announcement = request.POST.get('announcement', '').strip()
        contact_email = request.POST.get('contact_email', '').strip()
        online_store_email = request.POST.get('online_store_email', '').strip()
        contact_phone = request.POST.get('contact_phone', '').strip()
        instagram_handle = request.POST.get('instagram_handle', '').strip().lstrip('@')
        whatsapp_number = request.POST.get('whatsapp_number', '').strip()
        primary_color = request.POST.get('primary_color', '').strip()
        branch_id = request.POST.get('branch_id')

        store.is_active = is_active
        store.tagline = tagline
        store.announcement = announcement
        store.contact_email = contact_email
        store.online_store_email = online_store_email
        store.contact_phone = contact_phone
        store.instagram_handle = instagram_handle
        store.whatsapp_number = whatsapp_number

        if primary_color and primary_color.startswith('#'):
            store.primary_color = primary_color
            org.brand_color = primary_color
            org.save(update_fields=['brand_color'])

        if 'banner' in request.FILES and request.FILES['banner']:
            from ims.utils.image_optimizer import compress_image_to_webp
            if store.banner:
                try:
                    store.banner.delete(save=False)
                except Exception:
                    pass
            store.banner = compress_image_to_webp(request.FILES['banner'], max_dimension=1920, quality=85, prefix='banner')

        if branch_id:
            selected_branch = branches.filter(id=branch_id).first()
            if selected_branch:
                store.branch = selected_branch
                # Also synchronize organization default_branch
                org.default_branch = selected_branch
                org.save(update_fields=['default_branch'])

        store.save()
        messages.success(request, "Store settings updated successfully!")
        return redirect('store_settings')

    context = {
        'organization': org,
        'store': store,
        'branches': branches,
        'active_branch': store.get_active_branch(),
    }
    return render(request, 'store/vendor/store_settings.html', context)


@login_required
@role_required(['owner', 'manager'])
@require_online_store_access
def manage_listings(request):
    """
    Manage which inventory items appear on the public storefront.
    """
    org = get_request_organization(request)
    store, _ = StoreListing.objects.get_or_create(organization=org)
    branch = store.get_active_branch()

    if not branch:
        messages.warning(request, "Please set a default branch first in Store Settings.")
        return redirect('store_settings')

    is_htmx = bool(request.headers.get('HX-Request'))

    # Ensure all inventory items for this branch have a ProductListing record on full page load
    if not is_htmx and request.method == 'GET':
        branch_inventory = Inventory.objects.filter(
            branch=branch,
            organization=org
        ).select_related('product', 'product__category')

        for inv in branch_inventory:
            ProductListing.objects.get_or_create(
                store=store,
                inventory=inv,
                defaults={'is_visible': True}
            )

    all_branch_listings = ProductListing.objects.filter(
        store=store,
        inventory__branch=branch
    )

    # Handle quick toggle actions
    if request.method == 'POST':
        action = request.POST.get('action')
        listing_id = request.POST.get('listing_id')

        if action == 'toggle_visibility' and listing_id:
            item = get_object_or_404(ProductListing, id=listing_id, store=store)
            item.is_visible = not item.is_visible
            item.save(update_fields=['is_visible'])
            return JsonResponse({'success': True, 'is_visible': item.is_visible})

        elif action == 'toggle_featured' and listing_id:
            item = get_object_or_404(ProductListing, id=listing_id, store=store)
            item.featured = not item.featured
            item.save(update_fields=['featured'])
            return JsonResponse({'success': True, 'featured': item.featured})

        elif action == 'publish_all':
            all_branch_listings.update(is_visible=True)
            messages.success(request, "All branch products are now visible on your online store!")
            return redirect('manage_listings')

        elif action == 'hide_all':
            all_branch_listings.update(is_visible=False)
            messages.info(request, "All products have been hidden from your online store.")
            return redirect('manage_listings')

        elif action == 'edit_details' and listing_id:
            item = get_object_or_404(ProductListing, id=listing_id, store=store)
            item.custom_title = request.POST.get('custom_title', '').strip()
            item.custom_description = request.POST.get('custom_description', '').strip()
            from ims.utils.image_optimizer import optimize_product_image
            if 'image' in request.FILES:
                item.image = optimize_product_image(request.FILES['image'])
            if 'image_detail' in request.FILES:
                item.image_detail = optimize_product_image(request.FILES['image_detail'])
            if 'image_extra' in request.FILES:
                item.image_extra = optimize_product_image(request.FILES['image_extra'])
            item.save()
            messages.success(request, f"Updated '{item.display_title}' details.")
            return redirect('manage_listings')

    listings_qs = all_branch_listings.select_related(
        'inventory', 'inventory__product', 'inventory__product__category'
    ).order_by('-featured', 'inventory__product__product_name')

    search_query = request.GET.get('q', '').strip()
    if search_query:
        listings_qs = listings_qs.filter(
            models.Q(custom_title__icontains=search_query) |
            models.Q(inventory__product__product_name__icontains=search_query) |
            models.Q(inventory__product__product_code__icontains=search_query) |
            models.Q(inventory__product__category__category_name__icontains=search_query)
        )

    total_count = listings_qs.count()
    paginator = Paginator(listings_qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'organization': org,
        'store': store,
        'branch': branch,
        'listings': page_obj,
        'page_obj': page_obj,
        'total_count': total_count,
        'search_query': search_query,
    }

    if is_htmx:
        response = render(request, 'store/vendor/partials/listing_rows.html', context)
        response['HX-Trigger'] = json.dumps({'updateTotalCount': {'count': total_count}})
        return response

    return render(request, 'store/vendor/manage_listings.html', context)


@login_required
@role_required(['owner', 'manager', 'cashier'])
@require_online_store_access
def vendor_order_list(request):
    """
    Vendor dashboard for incoming online orders.
    """
    org = get_request_organization(request)
    status_filter = request.GET.get('status', '').strip()
    query = request.GET.get('q', '').strip()

    orders = OnlineOrder.objects.filter(organization=org).prefetch_related('items')

    if status_filter:
        orders = orders.filter(status=status_filter)

    if query:
        orders = orders.filter(
            order_number__icontains=query
        ) | orders.filter(
            buyer_name__icontains=query
        ) | orders.filter(
            buyer_phone__icontains=query
        ) | orders.filter(
            buyer_email__icontains=query
        )

    # Order counts for tabs
    all_orders = OnlineOrder.objects.filter(organization=org)
    counts = {
        'all': all_orders.count(),
        'pending': all_orders.filter(status='pending').count(),
        'confirmed': all_orders.filter(status='confirmed').count(),
        'dispatched': all_orders.filter(status='dispatched').count(),
        'delivered': all_orders.filter(status='delivered').count(),
        'cancelled': all_orders.filter(status='cancelled').count(),
    }

    context = {
        'organization': org,
        'orders': orders,
        'status_filter': status_filter,
        'query': query,
        'counts': counts,
    }
    return render(request, 'store/vendor/order_list.html', context)


@login_required
@role_required(['owner', 'manager', 'cashier'])
@require_online_store_access
def vendor_order_detail(request, order_id):
    """
    Detailed vendor order fulfillment view.
    """
    org = get_request_organization(request)
    order = get_object_or_404(
        OnlineOrder.objects.prefetch_related('items', 'items__inventory', 'items__inventory__product'),
        id=order_id,
        organization=org
    )

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'confirm':
            # Confirm Order -> Create IMS Sale & deduct inventory stock
            if order.status != 'pending':
                messages.warning(request, f"Order is already {order.get_status_display()}.")
                return redirect('vendor_order_detail', order_id=order.id)

            branch = order.branch or org.default_branch or Branch.objects.filter(organization=org).first()
            if not branch:
                messages.error(request, "No branch assigned to fulfill this order.")
                return redirect('vendor_order_detail', order_id=order.id)

            # Check stock
            for item in order.items.all():
                inv = item.inventory
                avail = inv.store_quantity if (inv and hasattr(inv, 'store_quantity')) else (inv.quantity if inv else 0)
                if not inv or avail < item.quantity:
                    messages.error(request, f"Cannot confirm: insufficient stock for '{item.product_name}'. Available: {avail}.")
                    return redirect('vendor_order_detail', order_id=order.id)

            from .views import complete_order_sale
            sale = complete_order_sale(order, staff=request.user)

            messages.success(request, f"Order #{order.order_number} confirmed! IMS Sale #{sale.id if sale else ''} created and inventory deducted.")
            return redirect('vendor_order_detail', order_id=order.id)

        elif action == 'dispatch':
            # Mark dispatched / In Transit
            courier = request.POST.get('courier_name', '').strip()
            tracking = request.POST.get('tracking_number', '').strip()
            dispatch_note = request.POST.get('dispatch_note', '').strip()

            order.courier_name = courier
            order.tracking_number = tracking
            order.dispatch_note = dispatch_note
            order.dispatched_at = timezone.now()
            order.status = 'dispatched'
            order.save(update_fields=['courier_name', 'tracking_number', 'dispatch_note', 'dispatched_at', 'status', 'updated_at'])

            messages.success(request, f"Order #{order.order_number} marked as Dispatched!")
            return redirect('vendor_order_detail', order_id=order.id)

        elif action == 'deliver':
            # Mark delivered
            order.delivered_at = timezone.now()
            order.status = 'delivered'
            order.save(update_fields=['delivered_at', 'status', 'updated_at'])

            messages.success(request, f"Order #{order.order_number} marked as Delivered!")
            return redirect('vendor_order_detail', order_id=order.id)

        elif action == 'cancel':
            # Cancel order and restore stock if already confirmed
            reason = request.POST.get('cancelled_reason', '').strip()

            with transaction.atomic():
                if order.status in ('confirmed', 'dispatched') and order.sale:
                    # Restore inventory
                    for item in order.items.all():
                        if item.inventory:
                            item.inventory.quantity = (item.inventory.quantity or 0) + item.quantity
                            item.inventory.quantity_available = (item.inventory.quantity_available or 0) + item.quantity
                            item.inventory.status = 'Available'
                            item.inventory.save(update_fields=['quantity', 'quantity_available', 'status'])

                order.cancelled_reason = reason
                order.cancelled_at = timezone.now()
                order.status = 'cancelled'
                order.save(update_fields=['cancelled_reason', 'cancelled_at', 'status', 'updated_at'])

            messages.info(request, f"Order #{order.order_number} has been cancelled.")
            return redirect('vendor_order_detail', order_id=order.id)

    context = {
        'organization': org,
        'order': order,
    }
    return render(request, 'store/vendor/order_detail.html', context)


@login_required
@role_required(['owner', 'manager'])
@require_online_store_access
def vendor_discounts(request):
    """
    Create and manage storefront coupons and promotional discounts.
    """
    org = get_request_organization(request)
    store, _ = StoreListing.objects.get_or_create(organization=org)
    discounts = StoreDiscount.objects.filter(organization=org).prefetch_related('redemptions')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            code = request.POST.get('code', '').strip().upper()
            label = request.POST.get('label', '').strip()
            discount_type = request.POST.get('discount_type', 'percent')
            value = Decimal(str(request.POST.get('value', '0') or 0))
            max_uses = int(request.POST.get('max_uses', 0) or 0)
            end_date_str = request.POST.get('end_date')

            if not code:
                # Generate random promo code
                code = f"QS-{secrets.token_hex(3).upper()}"

            if StoreDiscount.objects.filter(organization=org, code=code).exists():
                messages.error(request, f"A discount with code '{code}' already exists.")
                return redirect('vendor_discounts')

            end_date = None
            if end_date_str:
                try:
                    end_date = timezone.datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
                except ValueError:
                    pass

            StoreDiscount.objects.create(
                organization=org,
                branch=store.get_active_branch(),
                code=code,
                label=label,
                discount_type=discount_type,
                value=value,
                max_uses=max_uses,
                end_date=end_date,
                is_active=True
            )
            messages.success(request, f"Coupon '{code}' created successfully!")
            return redirect('vendor_discounts')

        elif action == 'toggle_active':
            disc_id = request.POST.get('discount_id')
            disc = get_object_or_404(StoreDiscount, id=disc_id, organization=org)
            disc.is_active = not disc.is_active
            disc.save(update_fields=['is_active'])
            return JsonResponse({'success': True, 'is_active': disc.is_active})

        elif action == 'delete':
            disc_id = request.POST.get('discount_id')
            disc = get_object_or_404(StoreDiscount, id=disc_id, organization=org)
            disc.delete()
            messages.success(request, "Discount coupon deleted.")
            return redirect('vendor_discounts')

    context = {
        'organization': org,
        'store': store,
        'discounts': discounts,
    }
    return render(request, 'store/vendor/discounts.html', context)


def calculate_organization_balances(org):
    """
    Computes settled online revenue (paid online orders + paid service enrollments),
    completed payouts, pending/processing payouts, and available balance for withdrawal.
    """
    paid_online_orders = OnlineOrder.objects.filter(
        organization=org,
        payment_status='paid',
        payment_method__in=['bachs', 'squadco'],
    ).exclude(status='cancelled')
    order_gross_revenue = paid_online_orders.aggregate(total=models.Sum('total_amount'))['total'] or Decimal('0.00')

    # Paid service/class enrollments
    paid_enrollments = ServiceEnrollment.objects.filter(
        organization=org,
        payment_status='paid'
    )
    service_settled_ngn = paid_enrollments.aggregate(total=models.Sum('settled_amount_ngn'))['total'] or Decimal('0.00')
    service_revenue_ngn = paid_enrollments.filter(currency='NGN').aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    service_revenue_usd = paid_enrollments.filter(currency='USD').aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

    total_gross_revenue = order_gross_revenue + service_settled_ngn

    completed_payouts = StorePayout.objects.filter(
        organization=org,
        status='completed'
    ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

    pending_payouts = StorePayout.objects.filter(
        organization=org,
        status__in=['pending', 'processing']
    ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

    available_balance = max(Decimal('0.00'), total_gross_revenue - completed_payouts - pending_payouts)

    return {
        'total_gross_revenue': total_gross_revenue,
        'order_gross_revenue': order_gross_revenue,
        'service_settled_ngn': service_settled_ngn,
        'service_revenue_ngn': service_revenue_ngn,
        'service_revenue_usd': service_revenue_usd,
        'completed_payouts': completed_payouts,
        'pending_payouts': pending_payouts,
        'available_balance': available_balance,
    }


def request_organization_payout(org, user, amount, notes='', idempotency_key=None):
    """
    Atomically verifies settled balance and minimum withdrawal, creates a StorePayout,
    and immediately disburses via Bachs when Bachs is the active gateway.
    """
    from subscriptions.models import PaymentGatewayConfig
    from .payout_service import disburse_store_payout

    try:
        amount = validate_positive_amount(amount, field_name="withdrawal amount")
    except ValueError as exc:
        return False, str(exc), None

    min_withdrawal = PaymentGatewayConfig.get_minimum_withdrawal_ngn()
    if amount < min_withdrawal:
        return False, f"Minimum withdrawal amount is ₦{min_withdrawal:,.2f}.", None

    cleaned_key = (str(idempotency_key).strip()[:64] if idempotency_key else None) or None

    with transaction.atomic():
        # Lock organization row to serialize all withdrawal transactions for this tenant
        locked_org = Organization.objects.select_for_update().get(id=org.id)

        # Idempotency check by explicit key
        if cleaned_key:
            existing_by_key = StorePayout.objects.filter(
                organization=locked_org,
                idempotency_key=cleaned_key
            ).first()
            if existing_by_key:
                return True, f"Withdrawal request #{existing_by_key.reference} is already being processed.", existing_by_key

        bank_account = StoreBankAccount.objects.filter(organization=locked_org).first()
        if not bank_account or not bank_account.account_number or not bank_account.bank_name:
            return False, "Please add your settlement bank account details before requesting a withdrawal.", None

        # Check for rapid duplicate submissions (within 10 seconds for exact same amount)
        recent_cutoff = timezone.now() - timezone.timedelta(seconds=10)
        recent_dup = StorePayout.objects.filter(
            organization=locked_org,
            amount=amount,
            status='pending',
            created_at__gte=recent_cutoff
        ).first()
        if recent_dup:
            return True, f"Withdrawal request #{recent_dup.reference} is already being processed.", recent_dup

        # Re-verify available balance inside the atomic lock
        balances = calculate_organization_balances(locked_org)
        avail = balances['available_balance']

        if amount > avail:
            return False, f"Requested amount (₦{amount:,.2f}) exceeds your available balance (₦{avail:,.2f}).", None

        active_gateway = get_active_gateway_name()
        payout = StorePayout.objects.create(
            organization=locked_org,
            idempotency_key=cleaned_key,
            amount=amount,
            currency='NGN',
            gateway=active_gateway,
            bank_name=bank_account.bank_name,
            account_number=bank_account.account_number,
            account_name=bank_account.account_name,
            status='pending',
            notes=notes,
            requested_by=user
        )
        if active_gateway == 'bachs':
            try:
                disburse_store_payout(
                    payout,
                    bank_account,
                    actor_label=f"auto ({getattr(user, 'email', 'merchant')})",
                )
            except Exception as exc:
                payout.status = 'rejected'
                payout.admin_notes = (
                    (payout.admin_notes + '\n' if payout.admin_notes else '')
                    + f'Automatic Bachs disbursement failed: {exc}'
                )
                payout.save(update_fields=['status', 'admin_notes'])
                return False, f"Withdrawal could not be processed: {exc}", None

            status_phrase = (
                "has been sent" if payout.status == 'completed' else "is being processed"
            )
            return (
                True,
                f"Withdrawal #{payout.reference} for ₦{amount:,.2f} {status_phrase} to {bank_account.bank_name} ({bank_account.account_number}).",
                payout,
            )

        return True, f"Withdrawal request #{payout.reference} for ₦{amount:,.2f} submitted successfully! It will be reviewed and processed to {bank_account.bank_name} ({bank_account.account_number}).", payout


@login_required
@role_required(['owner', 'manager'])
@require_online_store_access
def vendor_payouts(request):
    """
    Vendor wallet, revenue balances, settlement bank settings, and withdrawal requests.
    """
    org = get_request_organization(request)
    store, _ = StoreListing.objects.get_or_create(organization=org)
    bank_account, _ = StoreBankAccount.objects.get_or_create(
        organization=org,
        defaults={'bank_name': '', 'account_number': '', 'account_name': ''}
    )

    balances = calculate_organization_balances(org)
    payouts = StorePayout.objects.filter(organization=org).order_by('-created_at')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_bank':
            from .payout_service import resolve_bank_code
            bank_name = request.POST.get('bank_name', '').strip()
            bank_code = resolve_bank_code(bank_name, request.POST.get('bank_code', ''))
            account_number = request.POST.get('account_number', '').strip()
            account_name = request.POST.get('account_name', '').strip()

            if not bank_name or not account_number or not account_name:
                messages.error(request, "Please fill in bank name, account number, and account name.")
                return redirect('vendor_payouts')

            changed = (
                bank_account.bank_name != bank_name
                or bank_account.account_number != account_number
                or (bank_code and bank_account.bank_code != bank_code)
            )
            bank_account.bank_name = bank_name
            if bank_code:
                bank_account.bank_code = bank_code
            bank_account.account_number = account_number
            bank_account.account_name = account_name
            if changed:
                # Invalidate any previous Bachs destination ID so payouts cannot target a stale account
                bank_account.bachs_destination_id = None

            if get_active_gateway_name() == 'bachs' and bank_account.bank_code and settings.BACHS_API_KEY:
                try:
                    dest = BachsGateway().create_payout_destination(
                        currency='NGN',
                        account_number=bank_account.account_number,
                        bank_code=bank_account.bank_code,
                        name=bank_account.account_name,
                    )
                    bank_account.bachs_destination_id = dest['destination_id']
                except Exception as exc:
                    logger.warning("[Vendor Payouts] Could not pre-register Bachs destination: %s", exc)

            bank_account.save()
            messages.success(request, "Settlement bank account details updated successfully!")
            return redirect('vendor_payouts')

        elif action == 'request_payout':
            try:
                amount_val = Decimal(str(request.POST.get('amount', '0')).strip())
            except Exception:
                amount_val = Decimal('0.00')

            notes = request.POST.get('notes', '').strip()
            idempotency_key = request.POST.get('idempotency_key', '').strip() or None
            success, msg, _ = request_organization_payout(
                org, request.user, amount_val, notes=notes, idempotency_key=idempotency_key
            )
            if success:
                messages.success(request, msg)
            else:
                messages.error(request, msg)

            return redirect('vendor_payouts')

    from subscriptions.models import PaymentGatewayConfig
    min_withdrawal = PaymentGatewayConfig.get_minimum_withdrawal_ngn()

    context = {
        'organization': org,
        'store': store,
        'bank_account': bank_account,
        'total_gross_revenue': balances['total_gross_revenue'],
        'completed_payouts': balances['completed_payouts'],
        'pending_payouts': balances['pending_payouts'],
        'available_balance': balances['available_balance'],
        'min_withdrawal': min_withdrawal,
        'payouts': payouts,
    }
    return render(request, 'store/vendor/payouts.html', context)


@login_required
@role_required(['owner', 'manager', 'cashier'])
@require_online_store_access
def vendor_customers(request):
    """
    Analytics and directory of storefront customers, top spenders, and buyer profiles.
    """
    org = get_request_organization(request)
    store, _ = StoreListing.objects.get_or_create(organization=org)
    query = request.GET.get('q', '').strip().lower()
    tier_filter = request.GET.get('tier', '').strip().lower()

    # Query all online orders for this org
    orders = OnlineOrder.objects.filter(organization=org).select_related('buyer').prefetch_related('items').order_by('-created_at')

    # Aggregate customers by email
    customers_map = {}
    for o in orders:
        email = (o.buyer_email or (o.buyer.email if o.buyer else '')).strip().lower()
        if not email:
            continue
        if email not in customers_map:
            customers_map[email] = {
                'email': email,
                'name': o.buyer_name or (o.buyer.get_full_name() if o.buyer else email),
                'phone': o.buyer_phone or (o.buyer.phone_number if o.buyer else ''),
                'address': o.shipping_address or (o.buyer.shipping_address if o.buyer else ''),
                'orders_count': 0,
                'completed_orders_count': 0,
                'total_spent': Decimal('0.00'),
                'last_order_date': o.created_at,
                'last_order_number': o.order_number,
                'orders': [],
                'buyer_id': str(o.buyer.id) if o.buyer else None,
            }

        cust = customers_map[email]
        cust['orders_count'] += 1
        if o.status in ('confirmed', 'dispatched', 'delivered') or o.payment_status == 'paid':
            cust['completed_orders_count'] += 1
            cust['total_spent'] += o.total_amount
        if o.created_at >= cust['last_order_date']:
            cust['last_order_date'] = o.created_at
            cust['last_order_number'] = o.order_number
            if o.buyer_name:
                cust['name'] = o.buyer_name
            if o.buyer_phone:
                cust['phone'] = o.buyer_phone
            if o.shipping_address:
                cust['address'] = o.shipping_address

        cust['orders'].append({
            'order_number': o.order_number,
            'status': o.status,
            'status_display': o.get_status_display(),
            'total_amount': float(o.total_amount),
            'currency': o.currency,
            'created_at': o.created_at.strftime('%b %d, %Y %H:%M'),
            'payment_status': o.payment_status,
            'items_count': o.items.count() if hasattr(o, 'items') else 1,
        })

    customers_list = list(customers_map.values())

    # Assign badges / tiers
    for c in customers_list:
        if c['total_spent'] >= Decimal('50000.00') or c['orders_count'] >= 5:
            c['tier'] = 'vip'
            c['tier_label'] = 'VIP'
            c['tier_badge'] = 'bg-warning text-dark'
        elif c['orders_count'] >= 2:
            c['tier'] = 'repeat'
            c['tier_label'] = 'Repeat'
            c['tier_badge'] = 'bg-primary text-white'
        else:
            c['tier'] = 'new'
            c['tier_label'] = 'New'
            c['tier_badge'] = 'bg-light text-dark border'

    # Sort customers by total spend descending
    customers_list.sort(key=lambda x: (x['total_spent'], x['orders_count']), reverse=True)

    # Add ranking
    for idx, c in enumerate(customers_list, 1):
        c['rank'] = idx

    # Top VIPs (Top 5)
    top_customers = customers_list[:5]

    # Overall metrics
    total_customers_count = len(customers_list)
    repeat_customers_count = sum(1 for c in customers_list if c['orders_count'] >= 2)
    repeat_rate = round((repeat_customers_count / total_customers_count * 100), 1) if total_customers_count > 0 else 0
    total_customer_revenue = sum((c['total_spent'] for c in customers_list), Decimal('0.00'))
    avg_customer_spend = (total_customer_revenue / total_customers_count) if total_customers_count > 0 else Decimal('0.00')

    # Apply search filter
    filtered_customers = customers_list
    if query:
        filtered_customers = [
            c for c in filtered_customers
            if query in c['name'].lower() or query in c['email'].lower() or query in c['phone'].lower() or query in c['address'].lower()
        ]

    if tier_filter and tier_filter in ('vip', 'repeat', 'new'):
        filtered_customers = [c for c in filtered_customers if c['tier'] == tier_filter]

    context = {
        'organization': org,
        'store': store,
        'customers': filtered_customers,
        'top_customers': top_customers,
        'total_customers_count': total_customers_count,
        'repeat_customers_count': repeat_customers_count,
        'repeat_rate': repeat_rate,
        'total_customer_revenue': total_customer_revenue,
        'avg_customer_spend': avg_customer_spend,
        'query': query,
        'tier_filter': tier_filter,
    }
    return render(request, 'store/vendor/customers.html', context)


@login_required
@role_required(['owner', 'manager'])
@require_online_store_access
def manage_services(request):
    """
    Create, edit, toggle, and share Online Classes, Courses, and Services.
    Supports dual pricing: NGN (for Nigeria) and USD (for outside Nigeria),
    and stores the private class/access link sent automatically after payment.
    """
    org = get_request_organization(request)
    store, _ = StoreListing.objects.get_or_create(organization=org)

    if request.method == 'POST':
        action = request.POST.get('action', 'create').strip()

        if action in ('create', 'edit'):
            service_id = request.POST.get('service_id', '').strip()
            title = request.POST.get('title', '').strip()
            description = request.POST.get('description', '').strip()
            access_link = request.POST.get('access_link', '').strip()
            access_instructions = request.POST.get('access_instructions', '').strip()
            event_date_str = request.POST.get('event_date', '').strip()
            image_file = request.FILES.get('image')

            try:
                price_ngn = Decimal(str(request.POST.get('price_ngn', '0') or '0').strip())
            except Exception:
                price_ngn = Decimal('0.00')

            try:
                price_usd = Decimal(str(request.POST.get('price_usd', '0') or '0').strip())
            except Exception:
                price_usd = Decimal('0.00')

            try:
                usd_to_ngn_rate = Decimal(str(request.POST.get('usd_to_ngn_rate', '0') or '0').strip())
            except Exception:
                usd_to_ngn_rate = Decimal('0.00')

            try:
                max_participants = max(0, int(request.POST.get('max_participants', '0') or 0))
            except Exception:
                max_participants = 0

            if not title or not access_link:
                messages.error(request, "Please provide both the Class/Course Name and the Class Access Link.")
                return redirect('manage_services')

            event_date_val = None
            if event_date_str:
                for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
                    try:
                        naive_dt = timezone.datetime.strptime(event_date_str, fmt)
                        event_date_val = timezone.make_aware(naive_dt, timezone.get_current_timezone())
                        break
                    except ValueError:
                        continue

            if usd_to_ngn_rate <= Decimal('0.00'):
                if price_ngn > Decimal('0.00') and price_usd > Decimal('0.00'):
                    usd_to_ngn_rate = (price_ngn / price_usd).quantize(Decimal('0.01'))
                else:
                    usd_to_ngn_rate = Decimal('1500.00')

            if action == 'edit' and service_id:
                service = get_object_or_404(ServiceListing, id=service_id, organization=org)
                service.title = title
                service.description = description
                service.price_ngn = price_ngn
                service.price_usd = price_usd
                service.usd_to_ngn_rate = usd_to_ngn_rate
                service.access_link = access_link
                service.access_instructions = access_instructions
                service.event_date = event_date_val
                service.max_participants = max_participants
                if image_file:
                    service.image = image_file
                service.save()
                messages.success(request, f"Class/Service '{service.title}' updated successfully!")
            else:
                service = ServiceListing.objects.create(
                    organization=org,
                    store=store,
                    title=title,
                    description=description,
                    price_ngn=price_ngn,
                    price_usd=price_usd,
                    usd_to_ngn_rate=usd_to_ngn_rate,
                    access_link=access_link,
                    access_instructions=access_instructions,
                    event_date=event_date_val,
                    max_participants=max_participants,
                    image=image_file,
                    is_active=True,
                )
                messages.success(request, f"Class/Service '{service.title}' created! Copy its shareable link below.")

            return redirect('manage_services')

        elif action == 'toggle_active':
            service_id = request.POST.get('service_id')
            service = get_object_or_404(ServiceListing, id=service_id, organization=org)
            service.is_active = not service.is_active
            service.save(update_fields=['is_active', 'updated_at'])
            messages.success(request, f"'{service.title}' is now {'Active' if service.is_active else 'Closed'}.")
            return redirect('manage_services')

        elif action == 'delete':
            service_id = request.POST.get('service_id')
            service = get_object_or_404(ServiceListing, id=service_id, organization=org)
            title_copy = service.title
            service.delete()
            messages.success(request, f"Deleted '{title_copy}'.")
            return redirect('manage_services')

    services = list(
        ServiceListing.objects.filter(organization=org)
        .prefetch_related('enrollments')
        .order_by('-created_at')
    )

    for srv in services:
        all_enr = list(srv.enrollments.all())
        paid_enr = [e for e in all_enr if e.payment_status == 'paid']
        srv.applicants_total = len(all_enr)
        srv.paid_total = len(paid_enr)
        srv.revenue_ngn = sum((e.amount for e in paid_enr if e.currency == 'NGN'), Decimal('0.00'))
        srv.revenue_usd = sum((e.amount for e in paid_enr if e.currency == 'USD'), Decimal('0.00'))
        srv.settled_ngn_total = sum((e.settled_amount_ngn for e in paid_enr), Decimal('0.00'))
        srv.share_url = request.build_absolute_uri(
            reverse('service_landing', kwargs={'org_slug': org.slug, 'service_id': srv.id})
        )

    context = {
        'organization': org,
        'store': store,
        'services': services,
    }
    return render(request, 'store/vendor/services.html', context)


@login_required
@role_required(['owner', 'manager'])
@require_online_store_access
def service_enrollments_list(request, service_id=None):
    """
    Full history of all applicants (pending/applied) and paid students for a specific class
    or across all classes in the organization.
    Supports filtering, CSV export, and resending the class access link email.
    """
    org = get_request_organization(request)
    store, _ = StoreListing.objects.get_or_create(organization=org)

    selected_service = None
    if service_id:
        selected_service = get_object_or_404(ServiceListing, id=service_id, organization=org)

    if request.method == 'POST':
        action = request.POST.get('action')
        enrollment_id = request.POST.get('enrollment_id')
        if action == 'resend_email' and enrollment_id:
            enr = get_object_or_404(ServiceEnrollment, id=enrollment_id, organization=org)
            if enr.payment_status != 'paid':
                messages.warning(request, "Can only send the class access link to paid enrollments.")
            else:
                sent = send_service_enrollment_email(enr.id)
                if sent:
                    enr.access_email_sent = True
                    enr.access_email_sent_at = timezone.now()
                    enr.save(update_fields=['access_email_sent', 'access_email_sent_at', 'updated_at'])
                    messages.success(request, f"Class access link email resent to {enr.attendee_email}!")
                else:
                    messages.error(request, f"Could not send email to {enr.attendee_email}.")
            return redirect(request.get_full_path())

    qs = ServiceEnrollment.objects.filter(organization=org).select_related('service').order_by('-created_at')
    if selected_service:
        qs = qs.filter(service=selected_service)

    status_filter = request.GET.get('status', '').strip()
    currency_filter = request.GET.get('currency', '').strip().upper()
    search_query = request.GET.get('q', '').strip()

    if status_filter in ('pending', 'paid', 'failed'):
        qs = qs.filter(payment_status=status_filter)
    if currency_filter in ('NGN', 'USD'):
        qs = qs.filter(currency=currency_filter)
    if search_query:
        qs = (
            qs.filter(attendee_name__icontains=search_query)
            | qs.filter(attendee_email__icontains=search_query)
            | qs.filter(attendee_phone__icontains=search_query)
            | qs.filter(country__icontains=search_query)
            | qs.filter(enrollment_number__icontains=search_query)
            | qs.filter(payment_reference__icontains=search_query)
        )

    # CSV Export
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        filename = f"class_enrollments_{selected_service.slug if selected_service else org.slug}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)
        writer.writerow([
            'Enrollment #', 'Class / Service', 'Attendee Name', 'Email', 'Phone',
            'Country', 'City/State', 'Currency', 'Amount', 'Settled NGN (₦)',
            'Payment Status', 'Payment Reference', 'Applied At', 'Paid At', 'Email Sent'
        ])
        for e in qs:
            writer.writerow([
                e.enrollment_number,
                e.service.title,
                e.attendee_name,
                e.attendee_email,
                e.attendee_phone,
                e.country,
                e.city_state,
                e.currency,
                f"{e.amount:.2f}",
                f"{e.settled_amount_ngn:.2f}",
                e.get_payment_status_display(),
                e.payment_reference or '',
                e.created_at.strftime('%Y-%m-%d %H:%M') if e.created_at else '',
                e.paid_at.strftime('%Y-%m-%d %H:%M') if e.paid_at else '',
                'Yes' if e.access_email_sent else 'No',
            ])
        return response

    # Summary stats across the filtered class (or all classes)
    base_stats_qs = ServiceEnrollment.objects.filter(organization=org)
    if selected_service:
        base_stats_qs = base_stats_qs.filter(service=selected_service)

    total_applicants = base_stats_qs.count()
    total_paid = base_stats_qs.filter(payment_status='paid').count()
    total_pending = base_stats_qs.filter(payment_status='pending').count()
    revenue_ngn = base_stats_qs.filter(payment_status='paid', currency='NGN').aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    revenue_usd = base_stats_qs.filter(payment_status='paid', currency='USD').aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    settled_ngn_total = base_stats_qs.filter(payment_status='paid').aggregate(total=models.Sum('settled_amount_ngn'))['total'] or Decimal('0.00')

    paginator = Paginator(qs, 25)
    enrollments_page = paginator.get_page(request.GET.get('page'))

    all_services = ServiceListing.objects.filter(organization=org).order_by('title')

    context = {
        'organization': org,
        'store': store,
        'selected_service': selected_service,
        'all_services': all_services,
        'enrollments_page': enrollments_page,
        'status_filter': status_filter,
        'currency_filter': currency_filter,
        'search_query': search_query,
        'total_applicants': total_applicants,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'revenue_ngn': revenue_ngn,
        'revenue_usd': revenue_usd,
        'settled_ngn_total': settled_ngn_total,
    }
    return render(request, 'store/vendor/service_enrollments.html', context)


