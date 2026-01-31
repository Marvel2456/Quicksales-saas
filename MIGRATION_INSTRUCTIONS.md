"""
Database schema updates needed for offline-first sales system

This file shows the changes needed to the Sale model to track offline syncs.

Run these commands:
    python manage.py makemigrations ims
    python manage.py migrate ims

If you need to create this migration manually:
    python manage.py makemigrations ims --name add_offline_sync_fields
"""

# ADD THESE FIELDS TO ims/models.py → Sale class

# Around line 130 (after existing Sale model fields), add:

"""
    # Offline sync tracking (for offline-first feature)
    sync_from_offline = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this sale was synced from offline mode"
    )
    original_temp_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        unique=False,  # Can't be unique as multiple clients might generate same ID
        help_text="Original temporary ID from offline client for reference"
    )
    sync_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this sale was synced from offline (for tracking)"
    )
"""

# COMPLETE MIGRATION INSTRUCTIONS:

# 1. Open ims/models.py
# 2. Find the Sale model class
# 3. Add the three fields shown above (before the Meta class)
# 4. Save the file
# 5. Run: python manage.py makemigrations ims
# 6. Run: python manage.py migrate ims
# 7. Done!

# The migration will:
# - Add three new columns to ims_sale table
# - Create index on sync_from_offline for faster queries
# - Populate existing rows with default values
