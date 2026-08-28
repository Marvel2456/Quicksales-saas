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
        
        # Queue the expiry email separately so a mail failure never causes
        # the deactivation itself to be retried.
        owner = subscription.organization.owned_by
        if owner and owner.email:
            task_send_subscription_expired_email.delay(
                owner.id, subscription.organization.id, subscription_id
            )
            
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


# ---------------------------------------------------------------------------
# Queued email tasks — all email sending goes through Celery so that a slow
# or unavailable SMTP server never blocks a web request, and every email is
# retried automatically on failure.
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=5, default_retry_delay=60, name="task_send_verification_email")
def task_send_verification_email(self, user_id, organization_id):
    from .models import CustomUser, Organization
    from .emails import send_verification_email
    try:
        user = CustomUser.objects.get(id=user_id)
        org = Organization.objects.get(id=organization_id)
        send_verification_email(user, org)
        logger.info(f"Verification email sent to {user.email}")
    except Exception as exc:
        logger.error(f"task_send_verification_email failed for user {user_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=5, default_retry_delay=60, name="task_send_welcome_email")
def task_send_welcome_email(self, user_id, login_url):
    from .models import CustomUser
    from .emails import send_welcome_email
    try:
        user = CustomUser.objects.get(id=user_id)
        send_welcome_email(user, login_url)
        logger.info(f"Welcome email sent to {user.email}")
    except Exception as exc:
        logger.error(f"task_send_welcome_email failed for user {user_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=5, default_retry_delay=60, name="task_send_password_reset_email")
def task_send_password_reset_email(self, user_id, reset_link):
    from .models import CustomUser
    from .emails import send_password_reset_email
    try:
        user = CustomUser.objects.get(id=user_id)
        send_password_reset_email(user, reset_link)
        logger.info(f"Password reset email sent to {user.email}")
    except Exception as exc:
        logger.error(f"task_send_password_reset_email failed for user {user_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=5, default_retry_delay=60, name="task_send_subscription_success_email")
def task_send_subscription_success_email(self, user_id, organization_id, subscription_id):
    from .models import CustomUser, Organization
    from subscriptions.models import Subscription
    from .emails import send_subscription_success_email
    try:
        user = CustomUser.objects.get(id=user_id)
        org = Organization.objects.get(id=organization_id)
        subscription = Subscription.objects.get(id=subscription_id)
        send_subscription_success_email(user, org, subscription)
        logger.info(f"Subscription success email sent to {user.email}")
    except Exception as exc:
        logger.error(f"task_send_subscription_success_email failed for user {user_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=5, default_retry_delay=60, name="task_send_staff_invitation_email")
def task_send_staff_invitation_email(self, user_id, organization_id, branch_id, password, login_url):
    from .models import CustomUser, Organization, Branch
    from .emails import send_staff_invitation_email
    try:
        user = CustomUser.objects.get(id=user_id)
        org = Organization.objects.get(id=organization_id)
        branch = Branch.objects.get(id=branch_id)
        send_staff_invitation_email(user, org, branch, password, login_url)
        logger.info(f"Staff invitation email sent to {user.email}")
    except Exception as exc:
        logger.error(f"task_send_staff_invitation_email failed for user {user_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=5, default_retry_delay=60, name="task_send_staff_added_email")
def task_send_staff_added_email(self, to_email, org_name, role, login_url):
    """Plain notification email when an existing user is added to an org."""
    try:
        send_mail(
            subject=f'Added to {org_name}',
            message=f'You have been added to {org_name} as {role}. Login at {login_url}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            fail_silently=False,
        )
        logger.info(f"Staff-added email sent to {to_email}")
    except Exception as exc:
        logger.error(f"task_send_staff_added_email failed for {to_email}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=5, default_retry_delay=60, name="task_send_ticket_created_email")
def task_send_ticket_created_email(self, ticket_id, recipient_id, organization_id):
    from .models import CustomUser, Organization
    from .emails import send_ticket_created_email
    try:
        from ims.models import Ticket
        ticket = Ticket.objects.get(id=ticket_id)
        recipient = CustomUser.objects.get(id=recipient_id)
        org = Organization.objects.get(id=organization_id)
        send_ticket_created_email(ticket, recipient, org)
        logger.info(f"Ticket email sent to {recipient.email} for ticket {ticket_id}")
    except Exception as exc:
        logger.error(f"task_send_ticket_created_email failed ticket {ticket_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=5, default_retry_delay=60, name="task_send_subscription_expired_email")
def task_send_subscription_expired_email(self, user_id, organization_id, subscription_id):
    """Send the subscription-expired email to the owner (called by deactivate_subscription)."""
    from .models import CustomUser, Organization
    try:
        user = CustomUser.objects.get(id=user_id)
        org = Organization.objects.get(id=organization_id)
        subject = "Your Marvex Quicksales subscription has expired"
        html_message = render_to_string(
            "account/emails/trial_expired_email.html",
            {
                'user': user,
                'organization': org,
                'login_url': f"http://{org.slug}.{settings.DOMAIN}/subscriptions/settings/",
            }
        )
        plain_message = strip_tags(html_message)
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_message,
        )
        logger.info(f"Subscription expired email sent to {user.email}")
    except Exception as exc:
        logger.error(f"task_send_subscription_expired_email failed user {user_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60, name="task_send_promotional_campaign")
def task_send_promotional_campaign(self, campaign_id):
    """
    Sends promotional emails / newsletters to targeted organization owners in the background.
    Strictly isolated from transactional email workflows.
    """
    from .models import CustomUser, PromotionalCampaign, PromotionalEmailLog
    from subscriptions.models import Subscription

    try:
        campaign = PromotionalCampaign.objects.get(id=campaign_id)
    except PromotionalCampaign.DoesNotExist:
        logger.error(f"PromotionalCampaign {campaign_id} not found.")
        return

    campaign.status = 'Sending'
    campaign.save(update_fields=['status'])

    target = campaign.target_audience
    owners_qs = CustomUser.objects.filter(role='owner', is_active=True)

    if target == 'all_owners':
        recipients = list(owners_qs)
    elif target == 'selected_owners':
        recipients = list(campaign.recipient_owners.filter(is_active=True))
    elif target == 'active_subscribers':
        active_sub_user_ids = Subscription.objects.filter(status='active').values_list('user_id', flat=True)
        recipients = list(owners_qs.filter(id__in=active_sub_user_ids))
    elif target == 'trial_owners':
        trial_sub_user_ids = Subscription.objects.filter(status='trialing').values_list('user_id', flat=True)
        recipients = list(owners_qs.filter(id__in=trial_sub_user_ids))
    elif target == 'expired_subscribers':
        expired_sub_user_ids = Subscription.objects.filter(status='expired').values_list('user_id', flat=True)
        recipients = list(owners_qs.filter(id__in=expired_sub_user_ids))
    else:
        recipients = list(owners_qs)

    campaign.total_recipients = len(recipients)
    campaign.save(update_fields=['total_recipients'])

    sent_count = 0
    failed_count = 0

    for user in recipients:
        log_entry, _ = PromotionalEmailLog.objects.get_or_create(
            campaign=campaign,
            recipient=user,
            recipient_email=user.email
        )
        try:
            html_message = render_to_string(
                'account/emails/promotional_newsletter.html',
                {
                    'user': user,
                    'subject': campaign.subject,
                    'email_body': campaign.email_body,
                    'recipient_email': user.email,
                }
            )
            plain_message = strip_tags(html_message)

            send_mail(
                subject=campaign.subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False
            )

            log_entry.status = 'Sent'
            log_entry.error_message = None
            log_entry.sent_at = timezone.now()
            log_entry.save()
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed sending promotional email {campaign.id} to {user.email}: {e}")
            log_entry.status = 'Failed'
            log_entry.error_message = str(e)
            log_entry.save()
            failed_count += 1

    campaign.sent_count = sent_count
    campaign.failed_count = failed_count
    campaign.sent_at = timezone.now()
    campaign.status = 'Sent' if failed_count == 0 else ('Failed' if sent_count == 0 else 'Sent')
    campaign.save()

    logger.info(f"PromotionalCampaign {campaign.id} complete: {sent_count} sent, {failed_count} failed.")