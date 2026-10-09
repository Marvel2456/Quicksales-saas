import logging
from celery import shared_task
from .emails import send_buyer_order_confirmation_email, send_merchant_order_notification_email

logger = logging.getLogger(__name__)


@shared_task(name="task_send_buyer_order_confirmation_email")
def task_send_buyer_order_confirmation_email(order_id):
    """
    Celery task to asynchronously send order confirmation email to the buyer.
    """
    logger.info("[Celery Task] Dispatching order confirmation email for order ID: %s", order_id)
    return send_buyer_order_confirmation_email(order_id)


@shared_task(name="task_send_merchant_order_notification_email")
def task_send_merchant_order_notification_email(order_id):
    """
    Celery task to asynchronously send order notification email to shop owner and online store email.
    """
    logger.info("[Celery Task] Dispatching merchant order notification email for order ID: %s", order_id)
    return send_merchant_order_notification_email(order_id)

