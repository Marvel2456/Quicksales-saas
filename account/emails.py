from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator



def send_verification_email(user, organization):
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    domain = f"{organization.slug}.{settings.DOMAIN}"

    verification_url = f"http://{domain}/account/verify-email/{uid}/{token}/"

    subject = _("Verify your Marvex account")
    html_message = render_to_string('account/emails/verify_email.html', {
        'user': user,
        'verification_url': verification_url
    })
    plain_message = strip_tags(html_message)
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = user.email

    send_mail(subject, plain_message, from_email, [to_email], html_message=html_message)

# Welcome email for owner
def send_welcome_email(user, login_url):
    subject = _("Welcome to Marvex Quicksales")
    html_message = render_to_string('account/emails/welcome_email.html', {
        'user': user,
        'login_url': login_url,
    })
    plain_message = strip_tags(html_message)
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = user.email

    send_mail(subject, plain_message, from_email, [to_email], html_message=html_message)


# Password reset email
def send_password_reset_email(user, reset_link):
    subject = _("Password Reset Request")
    html_message = render_to_string('account/emails/password_reset_email.html', {'user': user, 'reset_link': reset_link})
    plain_message = strip_tags(html_message)
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = user.email

    send_mail(subject, plain_message, from_email, [to_email], html_message=html_message)



# Subscription renewal reminder email
def send_subscription_renewal_email(user, renewal_link):
    subject = _("Subscription Renewal Reminder")
    html_message = render_to_string('account/emails/subscription_renewal_email.html', {'user': user, 'renewal_link': renewal_link})
    plain_message = strip_tags(html_message)
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = user.email

    send_mail(subject, plain_message, from_email, [to_email], html_message=html_message)


# Trial expiry reminder email
def send_trial_expiry_email(user, expiry_date):
    subject = _("Trial Expiry Reminder")
    html_message = render_to_string('account/emails/trial_expiry_email.html', {'user': user, 'expiry_date': expiry_date})
    plain_message = strip_tags(html_message)
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = user.email

    send_mail(subject, plain_message, from_email, [to_email], html_message=html_message)