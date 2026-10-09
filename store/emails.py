import logging
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)


def send_buyer_order_confirmation_email(order_id):
    """
    Sends a beautifully formatted order confirmation email to the buyer (guest or registered)
    branded with the store's name, brand colors, itemized breakdown, and delivery details.
    """
    from .models import OnlineOrder, StoreListing

    try:
        order = OnlineOrder.objects.select_related('organization', 'buyer').prefetch_related('items').get(id=order_id)
    except OnlineOrder.DoesNotExist:
        logger.error("[Store Email] OnlineOrder with ID %s does not exist.", order_id)
        return False

    if not order.buyer_email:
        logger.warning("[Store Email] Order %s has no buyer email specified. Skipping email.", order.order_number)
        return False

    org = order.organization
    store = StoreListing.objects.filter(organization=org).first()
    store_name = (org.name if org else (store.organization.name if store else "Online Store")) or "Online Store"
    brand_color = store.get_brand_color if store else (getattr(org, 'brand_color', None) or "#2563eb")

    # Construct receipt URL
    protocol = "https" if (settings.ENV == "production" or not settings.DEBUG) else "http"
    domain = f"{org.slug}.{settings.DOMAIN}" if hasattr(settings, 'DOMAIN') and settings.DOMAIN else "localhost:8000"
    receipt_path = reverse('order_success', kwargs={'org_slug': org.slug, 'order_number': order.order_number})
    receipt_url = f"{protocol}://{domain}{receipt_path}"

    context = {
        'order': order,
        'order_number': order.order_number,
        'store_name': store_name,
        'brand_color': brand_color,
        'buyer_name': order.buyer_name or "Valued Customer",
        'buyer_email': order.buyer_email,
        'buyer_phone': order.buyer_phone,
        'shipping_address': order.shipping_address,
        'customer_notes': order.customer_notes,
        'currency': order.currency or "NGN",
        'subtotal': order.subtotal,
        'discount_amount': order.discount_amount,
        'total_amount': order.total_amount,
        'items': list(order.items.all()),
        'receipt_url': receipt_url,
        'organization': org,
    }

    subject = f"Order Confirmed: #{order.order_number} from {store_name}"
    html_content = render_to_string('store/emails/order_confirmation.html', context)
    text_content = render_to_string('store/emails/order_confirmation.txt', context)

    from_email = f"{store_name} <{settings.DEFAULT_FROM_EMAIL}>"
    recipient_list = [order.buyer_email]
    reply_email = (store.contact_email if store and store.contact_email else (getattr(org.owned_by, 'email', None) if org and getattr(org, 'owned_by', None) else None))

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=recipient_list,
            reply_to=[reply_email] if reply_email else None
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        logger.info("[Store Email] Successfully sent order confirmation email for order #%s to %s", order.order_number, order.buyer_email)
        return True
    except Exception as ex:
        logger.exception("[Store Email] Error sending order confirmation email for order #%s to %s: %s", order.order_number, order.buyer_email, ex)
        return False


def send_merchant_order_notification_email(order_id):
    """
    Sends an instant notification email to the shop owner and the configured online store email
    when an online order is successfully completed.
    Deduplicates recipient addresses so that if the online store email matches the owner's email,
    only one notification is sent.
    """
    from .models import OnlineOrder, StoreListing

    try:
        order = OnlineOrder.objects.select_related(
            'organization', 'organization__owned_by', 'buyer', 'branch'
        ).prefetch_related('items').get(id=order_id)
    except OnlineOrder.DoesNotExist:
        logger.error("[Store Merchant Email] OnlineOrder with ID %s does not exist.", order_id)
        return False

    org = order.organization
    store = StoreListing.objects.filter(organization=org).first()
    store_name = (org.name if org else (store.organization.name if store else "Online Store")) or "Online Store"
    brand_color = store.get_brand_color if store else (getattr(org, 'brand_color', None) or "#021024")

    # Resolve deduplicated recipient list (Owner + Online Store Email)
    recipients = []
    seen = set()

    def add_recipient(email_addr):
        if not email_addr:
            return
        cleaned = email_addr.strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            recipients.append(cleaned)

    # 1. Shop Owner's email
    if org and org.owned_by and org.owned_by.email:
        add_recipient(org.owned_by.email)
    elif org:
        owner_membership = org.memberships.filter(role='owner', is_active=True).select_related('user').first()
        if owner_membership and owner_membership.user and owner_membership.user.email:
            add_recipient(owner_membership.user.email)

    # 2. Configured Online Store Email (if distinct from owner)
    if store and store.online_store_email:
        add_recipient(store.online_store_email)

    if not recipients:
        logger.warning("[Store Merchant Email] No owner or online store email configured for org %s. Skipping notification.", getattr(org, 'slug', 'unknown'))
        return False

    # Construct dashboard order URL
    protocol = "https" if (getattr(settings, 'ENV', '') == "production" or not getattr(settings, 'DEBUG', True)) else "http"
    domain = getattr(settings, 'DOMAIN', '') or "localhost:8000"
    dashboard_path = reverse('vendor_order_detail', kwargs={'order_id': order.id})
    dashboard_order_url = f"{protocol}://{domain}{dashboard_path}"

    context = {
        'order': order,
        'order_number': order.order_number,
        'store_name': store_name,
        'brand_color': brand_color,
        'buyer_name': order.buyer_name or "Online Customer",
        'buyer_email': order.buyer_email,
        'buyer_phone': order.buyer_phone,
        'shipping_address': order.shipping_address,
        'customer_notes': order.customer_notes,
        'currency': order.currency or "NGN",
        'subtotal': order.subtotal,
        'discount_amount': order.discount_amount,
        'total_amount': order.total_amount,
        'items': list(order.items.all()),
        'dashboard_order_url': dashboard_order_url,
        'organization': org,
    }

    subject = f"🛍️ New Online Order #{order.order_number} Received — {store_name}"
    html_content = render_to_string('store/emails/merchant_order_notification.html', context)
    text_content = render_to_string('store/emails/merchant_order_notification.txt', context)

    from_email = f"{store_name} Notifications <{settings.DEFAULT_FROM_EMAIL}>"
    reply_email = order.buyer_email if order.buyer_email else None

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=recipients,
            reply_to=[reply_email] if reply_email else None
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        logger.info("[Store Merchant Email] Successfully sent merchant order notification for #%s to %s", order.order_number, recipients)
        return True
    except Exception as ex:
        logger.exception("[Store Merchant Email] Error sending order notification for #%s to %s: %s", order.order_number, recipients, ex)
        return False

