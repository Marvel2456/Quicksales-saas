from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator


def get_protocol():
    """Return https for production, http for development"""
    return 'https' if settings.ENV == 'production' else 'http'



def send_verification_email(user, organization):
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    domain = f"{organization.slug}.{settings.DOMAIN}"
    protocol = get_protocol()

    verification_url = f"{protocol}://{domain}/account/verify-email/{uid}/{token}/"

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
def send_trial_expiry_email(user, expiry_date, upgrade_url):
    subject = _("Trial Expiry Reminder")
    html_message = render_to_string(
        'account/emails/trial_expiry_email.html',
        {
            'user': user,
            'expiry_date': expiry_date,
            'upgrade_url': upgrade_url,
        },
    )
    plain_message = strip_tags(html_message)
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = user.email

    send_mail(subject, plain_message, from_email, [to_email], html_message=html_message)


def send_staff_invitation_email(user, organization, branch, password, login_url):
    """Send invitation email to new staff member with their credentials"""
    subject = _("Welcome to {} team on Marvex Quicksales".format(organization.name))
    
    context = {
        'user': user,
        'organization': organization,
        'branch': branch,
        'email': user.email,
        'password': password,
        'login_url': login_url,
    }
    
    html_message = render_to_string('account/emails/staff_invitation_email.html', context)
    plain_message = strip_tags(html_message)
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = user.email

    send_mail(
        subject,
        plain_message,
        from_email,
        [to_email],
        html_message=html_message
    )

# def send_staff_account_email(user, raw_password):
#     # domain = f"{organization.slug}.{settings.DOMAIN}"
#     """
#     Send email to staff with login credentials and organization dashboard link.
#     """
#     login_url = f"http://{user.organization.slug}.{settings.DOMAIN}/login/"
#     subject = f"Your {user.organization.name} Account Has Been Created"
#     message = (
#         f"Hello {user.get_full_name()},\n\n"
#         f"An account has been created for you at {user.organization.name}.\n\n"
#         f"Login here: {login_url}\n\n"
#         f"Email: {user.email}\n"
#         f"Password: {raw_password}\n\n"
#         f"Please change your password after logging in."
#     )
#     send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])


def send_staff_welcome_email(user, raw_password):
    protocol = get_protocol()
    login_url = f"{protocol}://{user.organization.slug}.{settings.DOMAIN}/account/login/"
    subject = f"Welcome to {user.organization.name}"
    message = (
        f"Hello {user.get_full_name()},\n\n"
        f"Your staff account has been created.\n\n"
        f"Email: {user.email}\n"
        f"Password: {raw_password}\n\n"
        f"You can log in here: {login_url}\n\n"
        "Please change your password after logging in."
    )
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def send_subscription_success_email(user, organization, subscription):
    """
    Send email notification when subscription is successfully activated
    """
    subject = _("Subscription Activated Successfully")
    
    protocol = get_protocol()
    context = {
        'user': user,
        'organization': organization,
        'subscription': subscription,
        'plan_name': subscription.plan.name,
        'start_date': subscription.start_date.strftime('%B %d, %Y'),
        'end_date': subscription.end_date.strftime('%B %d, %Y'),
        'dashboard_url': f"{protocol}://{organization.slug}.{settings.DOMAIN}/",
    }
    
    html_message = render_to_string('account/emails/subscription_success_email.html', context)
    plain_message = strip_tags(html_message)
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = user.email

    send_mail(
        subject,
        plain_message,
        from_email,
        [to_email],
        html_message=html_message,
        fail_silently=False,
    )


def send_ticket_created_email(ticket, assigned_to, organization):
    """
    Send email notification when a ticket is created and assigned to someone
    """
    subject = f"New Support Ticket: {ticket.title}"
    protocol = get_protocol()
    
    ticket_url = f"{protocol}://{organization.slug}.{settings.DOMAIN}/ims/ticket/{ticket.id}/"
    
    context = {
        'ticket': ticket,
        'assigned_to': assigned_to,
        'organization': organization,
        'ticket_url': ticket_url,
    }
    
    html_message = render_to_string('account/emails/ticket_created_email.html', context)
    plain_message = strip_tags(html_message)
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = assigned_to.email

    send_mail(
        subject,
        plain_message,
        from_email,
        [to_email],
        html_message=html_message,
        fail_silently=False,
    )
