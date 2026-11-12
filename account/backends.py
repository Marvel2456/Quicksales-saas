from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)


class CaseInsensitiveEmailBackend(ModelBackend):
    """
    Case-insensitive authentication backend for CustomUser.
    Matches emails using email__iexact so users can log in regardless of email casing,
    while passwords remain strictly case-sensitive.
    """
    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        UserModel = get_user_model()
        email_to_check = email or username or kwargs.get(UserModel.USERNAME_FIELD)
        if not email_to_check or not password:
            return None

        email_clean = email_to_check.strip().lower()
        try:
            user = UserModel._default_manager.get(email__iexact=email_clean)
        except UserModel.DoesNotExist:
            # Run the default password hasher once to reduce timing difference
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            # If multiple records exist historically, choose the active/latest one
            user = UserModel._default_manager.filter(
                email__iexact=email_clean
            ).order_by('-is_active', '-created_at').first()
            if not user:
                return None

        # Check password with full case-sensitivity
        if user.check_password(password) and self.user_can_authenticate(user):
            # Auto-heal legacy database record to lowercase if it had uppercase characters
            if user.email != user.email.lower():
                try:
                    user.email = user.email.lower()
                    user.save(update_fields=['email'])
                except Exception as exc:
                    logger.warning("Could not auto-heal uppercase email for user %s: %s", user.id, exc)
            return user
        return None

