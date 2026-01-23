from ims.models import Inventory
from django.db.models.signals import post_save
from django.dispatch import receiver
from account.models import Notification, CustomUser
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
import logging
import sys

logger = logging.getLogger(__name__)




@receiver(post_save, sender=Inventory)
def check_low_stock(sender, instance, created, **kwargs):
    """
    Check if inventory quantity falls below reorder level.
    If yes, create a notification and send email to organization owner.
    """
    print(f"[SIGNAL] Signal triggered for {instance.product.product_name if instance.product else 'Unknown'}", file=sys.stderr, flush=True)
    logger.info(f"Signal triggered for {instance.product.product_name if instance.product else 'Unknown'}")
    
    # Compute effective available quantity (uses store_quantity property when present)
    try:
        effective_qty = instance.store_quantity
    except Exception:
        effective_qty = instance.quantity

    # Only check if values exist (allow reorder_level = 0 explicitly)
    if instance.reorder_level is None or effective_qty is None:
        print(f"[SIGNAL] Skipping - reorder_level: {instance.reorder_level}, quantity: {effective_qty}")
        logger.info(f"Skipping - reorder_level: {instance.reorder_level}, quantity: {effective_qty}")
        return
    
    # Check if stock is at or below reorder level
    if effective_qty <= instance.reorder_level:
        print(f"[SIGNAL] LOW STOCK DETECTED: {instance.product.product_name} - Qty: {effective_qty}, Reorder: {instance.reorder_level}")
        logger.warning(f"LOW STOCK DETECTED: {instance.product.product_name} - Qty: {effective_qty}, Reorder: {instance.reorder_level}")
        
        organization = instance.organization
        branch = instance.branch
        
        # Only process if we have organization info
        if not organization:
            logger.error("No organization found for inventory")
            return
        
        # Get organization owner
        owner = organization.owned_by
        if not owner:
            msg = f"No owner found for organization {organization.name}"
            print(f"[SIGNAL] {msg}")
            logger.error(msg)
            return
        
        # Create notification for owner (unique per product+branch combination)
        branch_name = branch.name if branch else "Unknown"
        message = f"Low stock alert: {instance.product.product_name} in {branch_name} branch is now at {effective_qty} units (reorder level: {instance.reorder_level})"
        print(f"[SIGNAL] Creating notification: {message}")
        
        # Check if unread low stock notification already exists for this product+branch
        existing_notification = Notification.objects.filter(
            user=owner,
            notification_type='warning',
            message__icontains=f"Low stock alert: {instance.product.product_name} in {branch_name}",
            is_read=False
        ).first()
        
        if not existing_notification:
            # Create new notification
            notification = Notification.objects.create(
                user=owner,
                message=message,
                notification_type='warning',
                is_read=False
            )
            created_notification = True
        else:
            # Update existing notification with current quantity
            existing_notification.message = message
            existing_notification.save()
            created_notification = False
            notification = existing_notification
        
        if created_notification:
            print(f"[SIGNAL] ✓ New low stock detected - sending email")
            logger.info(f"Notification created for {owner.email}")
            
            # Send email ONLY when new notification is created (once per low stock occurrence)
            try:
                subject = f"Low Stock Alert - {organization.name}"
                context = {
                    'owner_name': owner.first_name or owner.email,
                    'organization_name': organization.name,
                    'product_name': instance.product.product_name,
                    'branch_name': branch_name,
                    'current_stock': effective_qty,
                    'reorder_level': instance.reorder_level,
                }
                
                # Try to render email template, fall back to simple text
                try:
                    html_message = render_to_string('emails/low_stock_alert.html', context)
                except Exception as template_error:
                    logger.warning(f"Template render failed: {template_error}, using fallback")
                    html_message = f"""
                    <h3>Low Stock Alert</h3>
                    <p>Dear {context['owner_name']},</p>
                    <p>Your product <strong>{context['product_name']}</strong> in the <strong>{context['branch_name']}</strong> branch is running low on stock.</p>
                    <p><strong>Current Stock:</strong> {context['current_stock']} units</p>
                    <p><strong>Reorder Level:</strong> {context['reorder_level']} units</p>
                    <p>Please consider placing a new order to replenish your inventory.</p>
                    <p>Best regards,<br>{context['organization_name']}</p>
                    """
                
                send_mail(
                    subject=subject,
                    message=f"Low Stock Alert: {context['product_name']} in {context['branch_name']} is at {context['current_stock']} units (reorder level: {context['reorder_level']})",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[owner.email],
                    html_message=html_message,
                    fail_silently=False  # Raise exceptions so we can see email errors
                )
                print(f"[SIGNAL] ✓ Email sent to {owner.email}")
                logger.info(f"Email sent to {owner.email} for {instance.product.product_name}")
            except Exception as e:
                print(f"[SIGNAL] ✗ Error sending email: {str(e)}")
                logger.error(f"Error sending low stock email to {owner.email}: {str(e)}")
        else:
            print(f"[SIGNAL] Notification already exists - no email sent (already notified)")
            logger.info(f"Notification already exists for {instance.product.product_name}")
    else:
        # Stock is above reorder level - mark any existing low stock notifications as read
        print(f"[SIGNAL] Stock OK: {instance.product.product_name} - Qty: {instance.quantity}, Reorder: {instance.reorder_level}")
        logger.info(f"Stock OK: {instance.product.product_name} - Qty: {instance.quantity}, Reorder: {instance.reorder_level}")
        
        # Auto-resolve low stock notifications when stock is restored
        organization = instance.organization
        branch = instance.branch
        if organization and branch:
            owner = organization.owned_by
            if owner:
                # Mark old low stock notifications for this product as read
                resolved_count = Notification.objects.filter(
                    user=owner,
                    notification_type='warning',
                    message__icontains=f"Low stock alert: {instance.product.product_name} in {branch.name}",
                    is_read=False
                ).update(is_read=True)
                
                if resolved_count > 0:
                    print(f"[SIGNAL] ✓ Auto-resolved {resolved_count} low stock notification(s) - stock restored")
                    logger.info(f"Auto-resolved {resolved_count} notifications for {instance.product.product_name}")
