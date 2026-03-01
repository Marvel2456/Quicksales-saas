# from procrastinate.contrib.django import app
# import logging
# from django.core.mail import send_mail
# from django.conf import settings
# from django.template.loader import render_to_string
# from django.utils.html import strip_tags
# from subscriptions.models import Subscription
# from .models import CustomUser

# logger = logging.getLogger('procrastinate')
# @app.task(name="deactivate_subscription")
# def deactivate_subscription(subscription_id: str):
#     """
#     Simplified task that only receives subscription_id
#     """
#     try:
#         subscription = Subscription.objects.select_related('organization').get(id=subscription_id)
#         subscription.is_active = False
#         subscription.save()
#         # ... email sending logic ...
#     except Subscription.DoesNotExist:
#         logger.error(f"Subscription {subscription_id} not found")
#         owner = subscription.organization.owned_by
#         if owner and owner.email:
#             subject = "Your Marvex Quicksales trial has expired"
#             html_message = render_to_string("account/emails/trial_expired_email.html", {
#                 'user': owner,
#                 'organization': subscription.organization,
#                 'login_url': f"http://{subscription.organization.slug}.{settings.DOMAIN}/upgrade/"
#             })
#             plain_message = strip_tags(html_message)

#             send_mail(
#                 subject,
#                 plain_message,
#                 settings.DEFAULT_FROM_EMAIL,
#                 [owner.email],
#                 html_message=html_message,
#             )

#     except Subscription.DoesNotExist:
#         print(f"Subscription {subscription_id} not found.")



# from procrastinate.contrib.django import app
# import logging
# from django.core.mail import send_mail
# from django.conf import settings
# from django.template.loader import render_to_string
# from django.utils.html import strip_tags

# logger = logging.getLogger("procrastinate")

# @app.task(name="deactivate_subscription")
# def deactivate_subscription(subscription_id: str):
#     # Import inside the function to avoid settings not loaded
#     from subscriptions.models import Subscription
#     from account.models import CustomUser

#     try:
#         subscription = Subscription.objects.select_related("organization").get(
#             id=subscription_id
#         )
#         subscription.is_active = False
#         subscription.save()

#     except Subscription.DoesNotExist:
#         logger.error(f"Subscription {subscription_id} not found")
#         return

#     owner = subscription.organization.owned_by
#     if owner and owner.email:
#         subject = "Your Marvex Quicksales trial has expired"
#         html_message = render_to_string(
#             "account/emails/trial_expired_email.html",
#             {
#                 "user": owner,
#                 "organization": subscription.organization,
#                 "login_url": f"http://{subscription.organization.slug}.{settings.DOMAIN}/upgrade/",
#             },
#         )
#         plain_message = strip_tags(html_message)

#         send_mail(
#             subject,
#             plain_message,
#             settings.DEFAULT_FROM_EMAIL,
#             [owner.email],
#             html_message=html_message,
#         )


from celery import shared_task
import logging
from datetime import timedelta
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from subscriptions.models import Subscription
from account.models import Organization, Notification
from account.emails import send_trial_expiry_email

logger = logging.getLogger(__name__)

@shared_task(name="deactivate_subscription", bind=True, max_retries=3)
def deactivate_subscription(self, subscription_id: str):
    """
    Deactivate subscription and send expiry email to owner
    """
    try:
        subscription = Subscription.objects.select_related(
            'organization', 
            'organization__owned_by'
        ).get(id=subscription_id)
        
        # Deactivate the subscription
        subscription.is_active = False
        subscription.save()
        
        logger.info(f"Deactivated subscription {subscription_id}")
        
        # Send email to owner
        owner = subscription.organization.owned_by
        if owner and owner.email:
            subject = "Your Marvex Quicksales trial has expired"
            html_message = render_to_string(
                "account/emails/trial_expired_email.html",
                {
                    'user': owner,
                    'organization': subscription.organization,
                    # Direct owner to subscription settings to upgrade/renew
                    'login_url': f"http://{subscription.organization.slug}.{settings.DOMAIN}/subscriptions/settings/",
                }
            )
            plain_message = strip_tags(html_message)

            send_mail(
                subject,
                plain_message,
                settings.DEFAULT_FROM_EMAIL,
                [owner.email],
                html_message=html_message,
            )
            logger.info(f"Sent expiry email to {owner.email}")
        else:
            logger.warning(f"No owner email found for subscription {subscription_id}")
            
    except Subscription.DoesNotExist:
        logger.error(f"Subscription {subscription_id} not found")
    except Exception as exc:
        logger.error(f"Error deactivating subscription {subscription_id}: {str(exc)}")
        # Retry after 60 seconds
        raise self.retry(exc=exc, countdown=60)


@shared_task(name="send_trial_expiry_reminders", bind=True, max_retries=3)
def send_trial_expiry_reminders(self):
    """
    Send a reminder email and in-app notification to org owners whose trial ends within 24 hours.
    Dedupe using recent reminder notifications (last 2 days) to avoid spamming.
    """
    try:
        now = timezone.now()
        window_end = now + timedelta(days=1)

        orgs = Organization.objects.select_related('owned_by').filter(
            trial_end__gte=now,
            trial_end__lte=window_end,
            is_active=True,
        )

        for org in orgs:
            owner = org.owned_by
            if not owner or not owner.email:
                continue

            # Deduplicate: skip if a recent reminder exists
            recent = Notification.objects.filter(
                user=owner,
                notification_type='warning',
                message__icontains='Trial ending soon',
                created_at__gte=now - timedelta(days=2),
            ).exists()
            if recent:
                continue

            # Create in-app notification
            Notification.objects.create(
                user=owner,
                message=(
                    f"Trial ending soon: {org.name} ends on "
                    f"{org.trial_end.strftime('%b %d, %Y %H:%M')}"
                ),
                notification_type='warning',
                organization=org,
                is_read=False,
            )

            # Send reminder email with upgrade link to subscription settings
            try:
                upgrade_url = f"http://{org.slug}.{settings.DOMAIN}/subscriptions/settings/"
                send_trial_expiry_email(owner, org.trial_end, upgrade_url)
            except Exception as email_exc:
                logger.error(f"Trial reminder email failed for {owner.email}: {email_exc}")

    except Exception as exc:
        logger.error(f"Error in send_trial_expiry_reminders: {exc}")
        raise self.retry(exc=exc, countdown=60)


@shared_task(name="send_subscription_expiry_reminders", bind=True, max_retries=3)
def send_subscription_expiry_reminders(self):
    """
    Send a reminder email and in-app notification to org owners whose subscription ends within 3 days.
    Dedupe using recent reminder notifications (last 3 days) to avoid spamming.
    """
    try:
        from subscriptions.models import Subscription
        from .emails import send_subscription_renewal_email
        
        now = timezone.now()
        # Check for subscriptions expiring within 3 days
        window_end = now + timedelta(days=3)

        subscriptions = Subscription.objects.select_related(
            'organization', 'organization__owned_by', 'plan'
        ).filter(
            is_active=True,
            end_date__gte=now,
            end_date__lte=window_end,
        )

        for subscription in subscriptions:
            org = subscription.organization
            owner = org.owned_by
            
            if not owner or not owner.email:
                continue

            # Deduplicate: skip if a recent reminder exists
            recent = Notification.objects.filter(
                user=owner,
                notification_type='warning',
                message__icontains='Subscription expiring soon',
                created_at__gte=now - timedelta(days=3),
            ).exists()
            if recent:
                continue

            # Calculate days remaining
            days_remaining = (subscription.end_date - now).days
            
            # Create in-app notification
            Notification.objects.create(
                user=owner,
                message=(
                    f"Subscription expiring soon: {subscription.plan.name} for {org.name} "
                    f"expires in {days_remaining} day(s) on {subscription.end_date.strftime('%b %d, %Y')}"
                ),
                notification_type='warning',
                organization=org,
                is_read=False,
            )

            # Send reminder email with renewal link
            try:
                renewal_url = f"{settings.DOMAIN}/subscriptions/settings/"
                send_subscription_renewal_email(owner, renewal_url)
                logger.info(f"Sent subscription renewal reminder to {owner.email} for {org.name}")
            except Exception as email_exc:
                logger.error(f"Subscription reminder email failed for {owner.email}: {email_exc}")

    except Exception as exc:
        logger.error(f"Error in send_subscription_expiry_reminders: {exc}")
        raise self.retry(exc=exc, countdown=60)