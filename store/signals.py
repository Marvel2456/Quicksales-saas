from django.db.models.signals import post_save
from django.dispatch import receiver
from ims.models import Inventory
from .models import StoreListing, ProductListing


@receiver(post_save, sender=Inventory)
def auto_create_product_listing(sender, instance, created, **kwargs):
    """
    Automatically creates a ProductListing on the organization's storefront
    whenever a new inventory item is added.
    """
    if not instance.organization:
        return

    store, _ = StoreListing.objects.get_or_create(organization=instance.organization)
    
    # If the listing does not exist yet, create it and make it visible
    ProductListing.objects.get_or_create(
        store=store,
        inventory=instance,
        defaults={'is_visible': True}
    )
