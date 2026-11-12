# Generated data migration to lowercase all existing user emails

from django.db import migrations
import logging

logger = logging.getLogger(__name__)


def lowercase_existing_user_emails(apps, schema_editor):
    CustomUser = apps.get_model('account', 'CustomUser')
    
    seen_emails = set()
    users_to_update = []
    
    # Process all users ordered by is_active descending, created_at descending
    for user in CustomUser.objects.all().order_by('-is_active', '-created_at'):
        raw_email = user.email or ''
        clean_email = raw_email.strip().lower()
        if not clean_email:
            continue
        
        if clean_email in seen_emails and clean_email != raw_email:
            # Duplicate collision with an existing lowercased user: keep unique
            logger.warning("Duplicate email collision encountered for user %s: %s", user.id, clean_email)
            continue
        
        seen_emails.add(clean_email)
        if raw_email != clean_email:
            user.email = clean_email
            user.save(update_fields=['email'])
            users_to_update.append(user.id)

    if users_to_update:
        logger.info("Lowercased %d existing CustomUser email(s).", len(users_to_update))

    # Also lowercase store Buyers if the table exists
    try:
        Buyer = apps.get_model('store', 'Buyer')
        for buyer in Buyer.objects.all():
            raw_email = buyer.email or ''
            clean_email = raw_email.strip().lower()
            if raw_email != clean_email:
                buyer.email = clean_email
                buyer.save(update_fields=['email'])
    except LookupError:
        pass


def reverse_lowercase_emails(apps, schema_editor):
    # Lowercasing is irreversible
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0016_customuser_permissions_and_more'),
    ]

    operations = [
        migrations.RunPython(lowercase_existing_user_emails, reverse_lowercase_emails),
    ]

