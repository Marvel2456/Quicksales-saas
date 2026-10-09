import uuid
import logging
import requests
from decimal import Decimal
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.urls import reverse

logger = logging.getLogger(__name__)

from account.models import Organization, Branch
from ims.models import Inventory, Category, Sale, SalesItem
from subscriptions.utils import has_online_store_access
from .models import (
    StoreListing, ProductListing, StoreDiscount, StoreDiscountRedemption,
    OnlineOrder, OnlineOrderItem, Buyer
)
from .buyer_auth import get_logged_in_buyer, buyer_login, buyer_logout, buyer_required


def _squad_headers():
    headers = {
        "Authorization": f"Bearer {settings.SQUAD_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    if settings.SQUAD_MERCHANT_ID:
        headers["MerchantId"] = settings.SQUAD_MERCHANT_ID
    return headers


def _extract_checkout_url(data):
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


def complete_order_sale(order, staff=None):
    """
    Atomically creates the IMS Sale record, SalesItems, and deducts branch inventory.
    Idempotent and thread-safe: uses select_for_update() row locking to prevent race conditions
    between concurrent webhook, callback, and vendor confirm triggers.
    """
    if not order:
        return None

    with transaction.atomic():
        # Lock the OnlineOrder row to prevent concurrent duplicate sales
        locked_order = OnlineOrder.objects.select_for_update().prefetch_related('items').get(id=order.id)
        if locked_order.sale_id:
            return locked_order.sale

        org = locked_order.organization
        branch = locked_order.branch or org.default_branch or Branch.objects.filter(organization=org).first()
        if not branch:
            return None

        sale = Sale.objects.create(
            organization=org,
            branch=branch,
            staff=staff,
            transaction_id=f"ONL-{locked_order.order_number}",
            final_total_price=float(locked_order.total_amount),
            discount=float(locked_order.discount_amount),
            method='SquadCo' if locked_order.payment_method == 'squadco' else 'Transfer',
            completed=True
        )

        total_profit = 0.0
        for item in locked_order.items.all():
            if item.inventory_id:
                # Lock inventory row to guarantee exact inventory deduction during concurrent transactions
                inv = Inventory.objects.select_for_update().get(id=item.inventory_id)
                unit_cost = float(inv.cost_price or 0.0)
                item_total = float(item.total_price)
                item_cost_total = unit_cost * item.quantity
                total_profit += (item_total - item_cost_total)

                SalesItem.objects.create(
                    organization=org,
                    branch=branch,
                    sale=sale,
                    inventory=inv,
                    quantity=item.quantity,
                    total=item_total,
                    cost_total=item_cost_total
                )

                inv.quantity = max(0, (inv.quantity or 0) - item.quantity)
                inv.quantity_available = max(0, (inv.quantity_available or 0) - item.quantity)
                if inv.quantity == 0:
                    inv.status = 'Restocking'
                inv.save(update_fields=['quantity', 'quantity_available', 'status'])

        sale.total_profit = total_profit
        sale.save(update_fields=['total_profit'])

        locked_order.sale = sale
        locked_order.status = 'confirmed'
        locked_order.payment_status = 'paid'
        if not locked_order.paid_at:
            locked_order.paid_at = timezone.now()
        locked_order.save(update_fields=['sale', 'status', 'payment_status', 'paid_at', 'updated_at'])

    # Asynchronously send order confirmation email to the buyer
    try:
        from .tasks import task_send_buyer_order_confirmation_email
        task_send_buyer_order_confirmation_email.delay(str(locked_order.id))
        logger.info("[Store Checkout] Dispatched async buyer confirmation email for order #%s", locked_order.order_number)
    except Exception as e:
        logger.warning("[Store Checkout] Celery async buyer email dispatch fallback (%s), sending directly...", e)
        try:
            from .emails import send_buyer_order_confirmation_email
            send_buyer_order_confirmation_email(locked_order.id)
        except Exception as e2:
            logger.exception("[Store Checkout] Failed sending buyer confirmation email: %s", e2)

    # Asynchronously send order notification email to the merchant / store owner & online store email
    try:
        from .tasks import task_send_merchant_order_notification_email
        task_send_merchant_order_notification_email.delay(str(locked_order.id))
        logger.info("[Store Checkout] Dispatched async merchant order notification email for order #%s", locked_order.order_number)
    except Exception as e:
        logger.warning("[Store Checkout] Celery async merchant email dispatch fallback (%s), sending directly...", e)
        try:
            from .emails import send_merchant_order_notification_email
            send_merchant_order_notification_email(locked_order.id)
        except Exception as e2:
            logger.exception("[Store Checkout] Failed sending merchant notification email: %s", e2)

    return sale


def _get_cart(request, org_slug):
    cart_key = f"store_cart_{org_slug}"
    return request.session.get(cart_key, {})


def _save_cart(request, org_slug, cart):
    cart_key = f"store_cart_{org_slug}"
    request.session[cart_key] = cart
    request.session.modified = True


def storefront(request, org_slug):
    """
    Public storefront for an organization.
    """
    org = get_object_or_404(Organization, slug=org_slug, is_active=True)
    store, _ = StoreListing.objects.get_or_create(organization=org)

    if not has_online_store_access(org) or not store.is_active:
        return render(request, 'store/store_inactive.html', {'organization': org})

    # Read default branch
    branch = store.get_active_branch()
    if not branch and org.branch_set.exists():
        branch = org.branch_set.first()
        if not org.default_branch:
            org.default_branch = branch
            org.save(update_fields=['default_branch'])

    # Auto-sync branch inventory into product listings so all items appear automatically
    if branch:
        branch_inventory = Inventory.objects.filter(
            organization=org,
            branch=branch
        )
        existing_inv_ids = set(ProductListing.objects.filter(store=store, inventory__branch=branch).values_list('inventory_id', flat=True))
        missing_invs = [inv for inv in branch_inventory if inv.id not in existing_inv_ids]
        if missing_invs:
            ProductListing.objects.bulk_create([
                ProductListing(store=store, inventory=inv, is_visible=True)
                for inv in missing_invs
            ])

    # Base query for visible listings
    listings = ProductListing.objects.filter(
        store=store,
        is_visible=True
    ).select_related('inventory', 'inventory__product', 'inventory__product__category')

    # Filter only listings where inventory matches the active branch if branch is assigned
    if branch:
        listings = listings.filter(inventory__branch=branch)

    # Search & category filter
    query = request.GET.get('q', '').strip()
    category_id = request.GET.get('category', '').strip()

    if query:
        listings = listings.filter(
            inventory__product__product_name__icontains=query
        ) | listings.filter(
            custom_title__icontains=query
        ) | listings.filter(
            inventory__product__brand__icontains=query
        )

    if category_id:
        listings = listings.filter(inventory__product__category_id=category_id)

    # Extract categories for sidebar/filter tabs
    categories = Category.objects.filter(
        organization=org
    ).distinct()

    featured_listings = listings.filter(featured=True)[:6]
    cart = _get_cart(request, org_slug)
    cart_count = sum(cart.values())
    buyer = get_logged_in_buyer(request)

    # Active store discounts for banners
    active_discount = StoreDiscount.objects.filter(
        organization=org,
        is_active=True,
        start_date__lte=timezone.now()
    ).exclude(end_date__lt=timezone.now()).first()

    # Check if logged in user is vendor owner or staff
    is_vendor_staff = False
    if request.user.is_authenticated:
        if org.owned_by == request.user:
            is_vendor_staff = True
        elif hasattr(org, 'memberships') and org.memberships.filter(user=request.user, role__in=['owner', 'manager', 'cashier']).exists():
            is_vendor_staff = True

    context = {
        'organization': org,
        'store': store,
        'branch': branch,
        'listings': listings,
        'featured_listings': featured_listings,
        'categories': categories,
        'selected_category': category_id,
        'query': query,
        'cart_count': cart_count,
        'buyer': buyer,
        'active_discount': active_discount,
        'is_vendor_staff': is_vendor_staff,
    }
    return render(request, 'store/storefront.html', context)


def product_detail(request, org_slug, listing_id):
    """
    Detailed single product page.
    """
    org = get_object_or_404(Organization, slug=org_slug, is_active=True)
    if not has_online_store_access(org):
        return render(request, 'store/store_inactive.html', {'organization': org})
    store = get_object_or_404(StoreListing, organization=org, is_active=True)
    listing = get_object_or_404(
        ProductListing.objects.select_related('inventory', 'inventory__product', 'inventory__product__category'),
        id=listing_id,
        store=store,
        is_visible=True
    )

    related_listings = ProductListing.objects.filter(
        store=store,
        is_visible=True,
        inventory__product__category=listing.inventory.product.category
    ).exclude(id=listing.id)[:4]

    cart = _get_cart(request, org_slug)
    cart_count = sum(cart.values())
    buyer = get_logged_in_buyer(request)

    context = {
        'organization': org,
        'store': store,
        'listing': listing,
        'related_listings': related_listings,
        'cart_count': cart_count,
        'buyer': buyer,
        'in_cart_qty': cart.get(str(listing.id), 0),
    }
    return render(request, 'store/product_detail.html', context)


def add_to_cart_api(request, org_slug):
    """
    AJAX endpoint to add an item to the buyer's store cart.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    import json
    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    listing_id = str(data.get('listing_id', ''))
    quantity = int(data.get('quantity', 1))

    if quantity < 1:
        quantity = 1

    org = get_object_or_404(Organization, slug=org_slug, is_active=True)
    if not has_online_store_access(org):
        return JsonResponse({'success': False, 'message': 'Online storefront is unavailable on this plan.'}, status=403)
    store = get_object_or_404(StoreListing, organization=org)
    listing = get_object_or_404(ProductListing, id=listing_id, store=store, is_visible=True)

    # Check available stock
    available = listing.stock_quantity
    cart = _get_cart(request, org_slug)
    current_qty = cart.get(listing_id, 0)
    new_qty = current_qty + quantity

    if new_qty > available:
        return JsonResponse({
            'success': False,
            'message': f"Only {available} items available in stock."
        }, status=400)

    cart[listing_id] = new_qty
    _save_cart(request, org_slug, cart)

    total_count = sum(cart.values())
    return JsonResponse({
        'success': True,
        'message': f"Added {listing.display_title} to bag.",
        'cart_count': total_count,
        'item_qty': new_qty
    })


def update_cart_api(request, org_slug):
    """
    Update item quantity or remove from cart.
    Returns refreshed calculation totals.
    Supports both explicit quantity or delta (+1 / -1).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    import json
    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    listing_id = str(data.get('listing_id', '')).strip()
    delta = data.get('delta')
    explicit_qty = data.get('quantity')
    coupon_code = str(data.get('coupon', '')).strip()

    org = get_object_or_404(Organization, slug=org_slug, is_active=True)
    if not has_online_store_access(org):
        return JsonResponse({'success': False, 'message': 'Online storefront is unavailable on this plan.'}, status=403)
    cart = _get_cart(request, org_slug)

    current_qty = cart.get(listing_id, 1)
    if delta is not None:
        try:
            quantity = max(0, current_qty + int(delta))
        except (ValueError, TypeError):
            quantity = current_qty
    elif explicit_qty is not None:
        try:
            quantity = max(0, int(explicit_qty))
        except (ValueError, TypeError):
            quantity = 0
    else:
        quantity = 0

    unit_price = Decimal('0.00')
    item_total = Decimal('0.00')
    if quantity <= 0:
        cart.pop(listing_id, None)
    else:
        listing = get_object_or_404(ProductListing, id=listing_id)
        unit_price = Decimal(str(listing.display_price or 0))
        available = listing.stock_quantity
        if quantity > available:
            return JsonResponse({
                'success': False,
                'message': f"Only {available} items available in stock."
            }, status=400)
        cart[listing_id] = quantity
        item_total = unit_price * quantity

    _save_cart(request, org_slug, cart)

    # Calculate full cart summary
    listings_map = {
        str(l.id): l for l in ProductListing.objects.filter(
            id__in=list(cart.keys()),
            is_visible=True
        )
    }
    subtotal = Decimal('0.00')
    for lid, qty in cart.items():
        l = listings_map.get(str(lid))
        if l:
            subtotal += Decimal(str(l.display_price or 0)) * qty

    discount_amount = Decimal('0.00')
    if coupon_code:
        disc = StoreDiscount.objects.filter(organization=org, code__iexact=coupon_code).first()
        if disc and disc.is_valid():
            if disc.discount_type == 'percent':
                discount_amount = (subtotal * disc.value) / Decimal('100.00')
            else:
                discount_amount = min(disc.value, subtotal)

    total_amount = max(Decimal('0.00'), subtotal - discount_amount)
    cart_count = sum(cart.values())

    return JsonResponse({
        'success': True,
        'cart_count': cart_count,
        'item_qty': quantity,
        'unit_price': float(unit_price),
        'item_total': float(item_total),
        'subtotal': float(subtotal),
        'discount_amount': float(discount_amount),
        'total_amount': float(total_amount),
        'cart_empty': cart_count == 0
    })


def store_checkout(request, org_slug):
    """
    Cart review, coupon redemption, and order placement.
    """
    org = get_object_or_404(Organization, slug=org_slug, is_active=True)
    if not has_online_store_access(org):
        return render(request, 'store/store_inactive.html', {'organization': org})
    store = get_object_or_404(StoreListing, organization=org, is_active=True)
    branch = store.get_active_branch()

    if not branch:
        messages.error(request, "This storefront is currently unavailable. Please contact the seller.")
        return redirect('storefront', org_slug=org_slug)

    cart = _get_cart(request, org_slug)
    if not cart:
        return redirect('storefront', org_slug=org_slug)

    # Fetch listing objects for cart items
    listing_ids = list(cart.keys())
    listings_map = {
        str(l.id): l for l in ProductListing.objects.filter(
            id__in=listing_ids,
            store=store,
            is_visible=True
        ).select_related('inventory', 'inventory__product')
    }

    cart_items = []
    subtotal = Decimal('0.00')

    for lid, qty in cart.items():
        listing = listings_map.get(str(lid))
        if not listing:
            continue
        unit_price = Decimal(str(listing.display_price or 0))
        item_total = unit_price * qty
        subtotal += item_total
        cart_items.append({
            'listing': listing,
            'quantity': qty,
            'unit_price': unit_price,
            'total_price': item_total,
            'available': listing.stock_quantity,
        })

    buyer = get_logged_in_buyer(request)
    discount_code = request.GET.get('coupon', '').strip() or request.POST.get('coupon_code', '').strip()
    discount = None
    discount_amount = Decimal('0.00')

    if discount_code:
        disc = StoreDiscount.objects.filter(organization=org, code__iexact=discount_code).first()
        if disc and disc.is_valid():
            discount = disc
            if disc.discount_type == 'percent':
                discount_amount = (subtotal * disc.value) / Decimal('100.00')
            else:
                discount_amount = min(disc.value, subtotal)
        else:
            messages.warning(request, f"Coupon '{discount_code}' is invalid or expired.")

    total_amount = max(Decimal('0.00'), subtotal - discount_amount)
    currency = 'NGN' if (org.country and org.country.lower() == 'nigeria') else 'USD'

    if request.method == 'POST' and ('place_order' in request.POST or request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == 'true'):
        is_ajax = (request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == 'true')
        buyer_name = request.POST.get('buyer_name', '').strip()
        buyer_email = request.POST.get('buyer_email', '').strip()
        buyer_phone = request.POST.get('buyer_phone', '').strip()
        street = request.POST.get('street_address', '').strip()
        city = request.POST.get('shipping_city', '').strip()
        state = request.POST.get('shipping_state', '').strip()
        country = request.POST.get('shipping_country', '').strip()
        
        shipping_parts = [p for p in [street, city, state, country] if p]
        if shipping_parts:
            shipping_address = ", ".join(shipping_parts)
        else:
            shipping_address = request.POST.get('shipping_address', '').strip()

        customer_notes = request.POST.get('customer_notes', '').strip()
        payment_method = 'squadco'
        payment_reference = f"QS-ORD-{uuid.uuid4().hex[:12].upper()}"

        if not buyer_name or not buyer_email or not buyer_phone:
            if is_ajax:
                return JsonResponse({'success': False, 'message': 'Please enter your name, email, and phone number.'}, status=400)
            messages.error(request, "Please enter your name, email, and phone number.")
            return render(request, 'store/checkout.html', {
                'organization': org,
                'store': store,
                'cart_items': cart_items,
                'subtotal': subtotal,
                'discount': discount,
                'discount_amount': discount_amount,
                'total_amount': total_amount,
                'currency': currency,
                'buyer': buyer,
                'squad_public_key': settings.SQUAD_PUBLIC_KEY,
            })

        # Check stock availability for all items
        for item in cart_items:
            listing = item['listing']
            if not listing or listing.stock_quantity < item['quantity']:
                msg = f"Sorry, '{item['listing'].display_title}' no longer has sufficient stock."
                if is_ajax:
                    return JsonResponse({'success': False, 'message': msg}, status=400)
                messages.error(request, msg)
                return redirect('store_checkout', org_slug=org_slug)

        if currency == 'NGN' and 0 < total_amount < Decimal('100.00'):
            msg = "The minimum online checkout amount with Squad is ₦100.00. Please increase your order quantity or add more items."
            if is_ajax:
                return JsonResponse({'success': False, 'message': msg}, status=400)
            messages.error(request, msg)
            return redirect('store_checkout', org_slug=org_slug)

        with transaction.atomic():
            # Create Online Order
            order = OnlineOrder.objects.create(
                organization=org,
                branch=branch,
                buyer=buyer,
                buyer_name=buyer_name,
                buyer_email=buyer_email,
                buyer_phone=buyer_phone,
                shipping_address=shipping_address,
                customer_notes=customer_notes,
                status='pending',
                payment_method=payment_method,
                payment_status='pending',
                payment_reference=payment_reference,
                currency=currency,
                subtotal=subtotal,
                discount_amount=discount_amount,
                total_amount=total_amount,
                discount=discount,
            )

            # Create line items
            for item in cart_items:
                OnlineOrderItem.objects.create(
                    order=order,
                    product_listing=item['listing'],
                    inventory=item['listing'].inventory,
                    product_name=item['listing'].display_title,
                    unit_price=item['unit_price'],
                    quantity=item['quantity'],
                    total_price=item['total_price'],
                )

            # Record coupon redemption if applicable
            if discount:
                StoreDiscountRedemption.objects.create(
                    discount=discount,
                    order=order,
                    buyer=buyer,
                    amount_saved=discount_amount
                )
                discount.uses += 1
                discount.save(update_fields=['uses'])

        # Free order handler (100% discount)
        if total_amount <= 0:
            complete_order_sale(order)
            _save_cart(request, org_slug, {})
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'free_order': True,
                    'redirect_url': reverse('order_success', kwargs={'org_slug': org_slug, 'order_number': order.order_number})
                })
            return redirect('order_success', org_slug=org_slug, order_number=order.order_number)

        callback_url = request.build_absolute_uri(
            reverse('store_payment_callback', kwargs={'org_slug': org_slug})
        )

        amount_minor = int(total_amount * 100)
        checkout_url = None
        squad_initiate_error = None

        logger.info(
            "[Store Checkout] Processing checkout for org '%s': buyer='%s' <%s>, phone='%s', amount=%s %s, items=%d",
            org_slug, buyer_name, buyer_email, buyer_phone, total_amount, currency, len(cart_items)
        )

        if settings.SQUAD_SECRET_KEY and settings.SQUAD_API_BASE_URL:
            initiate_url = f"{settings.SQUAD_API_BASE_URL.rstrip('/')}/transaction/initiate"
            logger.info("[Store Checkout] Initiating Squad payment at %s for ref %s (amount kobo: %s)", initiate_url, payment_reference, amount_minor)
            try:
                resp = requests.post(
                    initiate_url,
                    headers=_squad_headers(),
                    json={
                        "email": buyer_email,
                        "amount": amount_minor,
                        "currency": currency,
                        "initiate_type": "inline",
                        "transaction_ref": payment_reference,
                        "callback_url": f"{callback_url}?reference={payment_reference}",
                        "payment_channels": ["card", "bank", "ussd", "transfer"],
                    },
                    timeout=20
                )
                logger.info("[Store Checkout] Squad initiate HTTP %s: %s", resp.status_code, resp.text)
                if resp.status_code in (200, 201):
                    checkout_url = _extract_checkout_url(resp.json())
                else:
                    try:
                        err_data = resp.json()
                        squad_initiate_error = err_data.get('message') or f"Squad error: {resp.status_code}"
                    except Exception:
                        squad_initiate_error = f"Squad error (HTTP {resp.status_code})"
            except Exception as ex:
                logger.exception("[Store Checkout] Squad initiate exception: %s", ex)
                squad_initiate_error = "Could not connect to payment gateway. Please try again."

        if squad_initiate_error and not checkout_url:
            logger.warning("[Store Checkout] Failed to initiate: %s", squad_initiate_error)
            if is_ajax:
                return JsonResponse({'success': False, 'message': squad_initiate_error}, status=400)
            messages.error(request, squad_initiate_error)
            return redirect('store_checkout', org_slug=org_slug)

        if not checkout_url:
            api_base = (settings.SQUAD_API_BASE_URL or "").lower()
            checkout_host = "sandbox-pay.squadco.com" if "sandbox" in api_base else "pay.squadco.com"
            merchant_id = (settings.SQUAD_MERCHANT_ID or "").strip()
            if merchant_id:
                import base64
                enc = base64.b64encode(f"{merchant_id}|{payment_reference}".encode()).decode().rstrip('=')
                checkout_url = f"https://{checkout_host}/c_{enc}"
            else:
                checkout_url = f"https://{checkout_host}/{payment_reference}"

        logger.info("[Store Checkout] Ready: ref=%s, order=%s, checkout_url=%s", payment_reference, order.order_number, checkout_url)

        if is_ajax:
            return JsonResponse({
                'success': True,
                'reference': payment_reference,
                'amount': float(total_amount),
                'amount_kobo': amount_minor,
                'currency': currency,
                'buyer_email': buyer_email,
                'buyer_name': buyer_name,
                'public_key': settings.SQUAD_PUBLIC_KEY,
                'callback_url': callback_url,
                'checkout_url': checkout_url,
                'order_number': order.order_number,
            })

        return redirect(checkout_url)

    context = {
        'organization': org,
        'store': store,
        'cart_items': cart_items,
        'subtotal': subtotal,
        'discount': discount,
        'discount_amount': discount_amount,
        'total_amount': total_amount,
        'currency': currency,
        'buyer': buyer,
        'squad_public_key': settings.SQUAD_PUBLIC_KEY,
    }
    return render(request, 'store/checkout.html', context)


def store_payment_callback(request, org_slug):
    """
    SquadCo payment return / callback handler.
    Verifies transaction, creates IMS Sale, updates stock, and redirects to receipt.
    """
    org = get_object_or_404(Organization, slug=org_slug, is_active=True)
    reference = request.GET.get('reference') or request.GET.get('transaction_ref') or request.GET.get('trxref')

    logger.info("[Store Callback] Received return callback for org '%s', query params: %s", org_slug, dict(request.GET))

    if not reference:
        logger.warning("[Store Callback] No reference in callback request for org '%s'", org_slug)
        messages.error(request, "No transaction reference provided.")
        return redirect('storefront', org_slug=org_slug)

    order = OnlineOrder.objects.filter(
        organization=org,
        payment_reference=reference
    ).prefetch_related('items', 'items__inventory').first()

    if not order:
        logger.error("[Store Callback] OnlineOrder not found for ref '%s' in org '%s'", reference, org_slug)
        messages.error(request, "Order not found for transaction reference.")
        return redirect('storefront', org_slug=org_slug)

    # Verify with Squad API if secret key configured
    is_successful = False
    if settings.SQUAD_SECRET_KEY and settings.SQUAD_API_BASE_URL:
        verify_url = f"{settings.SQUAD_API_BASE_URL.rstrip('/')}/transaction/verify/{reference}"
        logger.info("[Store Callback] Verifying ref '%s' with Squad at %s", reference, verify_url)
        try:
            resp = requests.get(
                verify_url,
                headers=_squad_headers(),
                timeout=20
            )
            logger.info("[Store Callback] Squad verify HTTP %s: %s", resp.status_code, resp.text)
            if resp.status_code == 200:
                data = resp.json()
                status_str = str(data.get('data', {}).get('transaction_status') or data.get('data', {}).get('status') or '').lower()
                if status_str in ('success', 'successful', 'completed', 'approved'):
                    is_successful = True
        except Exception as ex:
            logger.exception("[Store Callback] Squad verification exception: %s", ex)

    logger.info("[Store Callback] Verification result for ref '%s': is_successful=%s, DEBUG=%s", reference, is_successful, settings.DEBUG)

    # Complete sale if verified or in test/sandbox
    if is_successful or order.payment_status == 'paid' or settings.DEBUG:
        complete_order_sale(order)
        _save_cart(request, org_slug, {})
        return redirect('order_success', org_slug=org_slug, order_number=order.order_number)
    else:
        order.payment_status = 'failed'
        order.save(update_fields=['payment_status', 'updated_at'])
        return redirect('store_checkout', org_slug=org_slug)


def order_success(request, org_slug, order_number):
    """
    Order receipt page.
    """
    org = get_object_or_404(Organization, slug=org_slug, is_active=True)
    store = get_object_or_404(StoreListing, organization=org)
    order = get_object_or_404(OnlineOrder.objects.prefetch_related('items'), organization=org, order_number=order_number)

    context = {
        'organization': org,
        'store': store,
        'order': order,
    }
    return render(request, 'store/order_success.html', context)


# ==========================================
# Buyer Portal (Authentication & Dashboard)
# ==========================================

def buyer_register_view(request):
    """
    Sign up for a universal Buyer account.
    """
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        shipping_address = request.POST.get('shipping_address', '').strip()

        if not email or not password:
            messages.error(request, "Email and password are required.")
            return render(request, 'store/buyer/register.html')

        if len(password) < 6:
            messages.error(request, "Password must be at least 6 characters.")
            return render(request, 'store/buyer/register.html')

        if Buyer.objects.filter(email=email).exists():
            messages.error(request, "An account with this email already exists. Please log in.")
            return redirect('buyer_login')

        buyer = Buyer(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            shipping_address=shipping_address,
            is_active=True,
            is_verified=True,
        )
        buyer.set_password(password)
        buyer.save()

        buyer_login(request, buyer)
        messages.success(request, f"Welcome, {buyer.first_name or buyer.email}!")
        next_url = request.GET.get('next') or reverse('buyer_dashboard')
        return redirect(next_url)

    return render(request, 'store/buyer/register.html')


def buyer_login_view(request):
    """
    Universal Buyer login across all stores.
    """
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        try:
            buyer = Buyer.objects.get(email=email, is_active=True)
            if buyer.check_password(password):
                buyer_login(request, buyer)
                messages.success(request, f"Welcome back, {buyer.first_name or buyer.email}!")
                next_url = request.GET.get('next') or reverse('buyer_dashboard')
                return redirect(next_url)
            else:
                messages.error(request, "Incorrect password.")
        except Buyer.DoesNotExist:
            messages.error(request, "No buyer account found with this email.")

    return render(request, 'store/buyer/login.html')


def buyer_logout_view(request):
    """
    Log out of the buyer account.
    """
    buyer_logout(request)
    messages.info(request, "You have been logged out.")
    return redirect(request.META.get('HTTP_REFERER', '/'))


@buyer_required
def buyer_dashboard_view(request):
    """
    View all orders across all vendor storefronts.
    """
    buyer = request.buyer
    orders = OnlineOrder.objects.filter(
        buyer=buyer
    ).select_related('organization').prefetch_related('items').order_by('-created_at')

    context = {
        'buyer': buyer,
        'orders': orders,
    }
    return render(request, 'store/buyer/dashboard.html', context)
