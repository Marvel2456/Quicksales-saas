from procrastinate.contrib.django import app
import logging
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from subscriptions.models import Subscription
from .models import CustomUser

logger = logging.getLogger('procrastinate')
@app.task(name="deactivate_subscription")
def deactivate_subscription(subscription_id: str):
    """
    Simplified task that only receives subscription_id
    """
    try:
        subscription = Subscription.objects.select_related('organization').get(id=subscription_id)
        subscription.is_active = False
        subscription.save()
        # ... email sending logic ...
    except Subscription.DoesNotExist:
        logger.error(f"Subscription {subscription_id} not found")
        owner = subscription.organization.owned_by
        if owner and owner.email:
            subject = "Your Marvex Quicksales trial has expired"
            html_message = render_to_string("account/emails/trial_expired_email.html", {
                'user': owner,
                'organization': subscription.organization,
                'login_url': f"http://{subscription.organization.slug}.{settings.DOMAIN}/upgrade/"
            })
            plain_message = strip_tags(html_message)

            send_mail(
                subject,
                plain_message,
                settings.DEFAULT_FROM_EMAIL,
                [owner.email],
                html_message=html_message,
            )

    except Subscription.DoesNotExist:
        print(f"Subscription {subscription_id} not found.")
