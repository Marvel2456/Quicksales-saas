"""
Cache Invalidation Signals
============================

Automatically invalidates cache when models are modified.
This ensures cached data stays in sync with database changes.
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from ims.models import Sale, SalesItem, Inventory, Product, Category
from ims.view_caching import get_invalidation_patterns


def invalidate_cache_patterns(org_id, patterns):
    """
    Invalidate cache entries matching the given patterns
    
    Args:
        org_id: Organization ID
        patterns: List of cache key patterns to invalidate
    """
    for pattern in patterns:
        try:
            # Django Redis doesn't support pattern deletion directly
            # We need to iterate through keys
            keys_to_delete = []
            for key in cache.keys(pattern):
                keys_to_delete.append(key)
            
            if keys_to_delete:
                cache.delete_many(keys_to_delete)
        except Exception as e:
            # Log in production
            pass


@receiver(post_save, sender=Sale)
def invalidate_sale_cache(sender, instance, created, **kwargs):
    """Invalidate cache when a Sale is created or updated"""
    patterns = get_invalidation_patterns('Sale', instance.organization_id)
    invalidate_cache_patterns(instance.organization_id, patterns)


@receiver(post_delete, sender=Sale)
def invalidate_sale_delete_cache(sender, instance, **kwargs):
    """Invalidate cache when a Sale is deleted"""
    patterns = get_invalidation_patterns('Sale', instance.organization_id)
    invalidate_cache_patterns(instance.organization_id, patterns)


@receiver(post_save, sender=SalesItem)
def invalidate_salesitem_cache(sender, instance, created, **kwargs):
    """Invalidate cache when a SalesItem is created or updated"""
    # Invalidate related sale and dashboard caches
    patterns = [
        f'sales_list:org:{instance.organization_id}:*',
        f'cart:org:{instance.organization_id}:*',
        f'dashboard:org:{instance.organization_id}:*',
    ]
    invalidate_cache_patterns(instance.organization_id, patterns)


@receiver(post_delete, sender=SalesItem)
def invalidate_salesitem_delete_cache(sender, instance, **kwargs):
    """Invalidate cache when a SalesItem is deleted"""
    patterns = [
        f'sales_list:org:{instance.organization_id}:*',
        f'cart:org:{instance.organization_id}:*',
        f'dashboard:org:{instance.organization_id}:*',
    ]
    invalidate_cache_patterns(instance.organization_id, patterns)


@receiver(post_save, sender=Inventory)
def invalidate_inventory_cache(sender, instance, created, **kwargs):
    """Invalidate cache when Inventory is created or updated"""
    patterns = get_invalidation_patterns('Inventory', instance.organization_id)
    invalidate_cache_patterns(instance.organization_id, patterns)


@receiver(post_delete, sender=Inventory)
def invalidate_inventory_delete_cache(sender, instance, **kwargs):
    """Invalidate cache when Inventory is deleted"""
    patterns = get_invalidation_patterns('Inventory', instance.organization_id)
    invalidate_cache_patterns(instance.organization_id, patterns)


@receiver(post_save, sender=Product)
def invalidate_product_cache(sender, instance, created, **kwargs):
    """Invalidate cache when Product is created or updated"""
    patterns = get_invalidation_patterns('Product', instance.organization_id)
    invalidate_cache_patterns(instance.organization_id, patterns)


@receiver(post_delete, sender=Product)
def invalidate_product_delete_cache(sender, instance, **kwargs):
    """Invalidate cache when Product is deleted"""
    patterns = get_invalidation_patterns('Product', instance.organization_id)
    invalidate_cache_patterns(instance.organization_id, patterns)


@receiver(post_save, sender=Category)
def invalidate_category_cache(sender, instance, created, **kwargs):
    """Invalidate cache when Category is created or updated"""
    patterns = get_invalidation_patterns('Category', instance.organization_id)
    invalidate_cache_patterns(instance.organization_id, patterns)


@receiver(post_delete, sender=Category)
def invalidate_category_delete_cache(sender, instance, **kwargs):
    """Invalidate cache when Category is deleted"""
    patterns = get_invalidation_patterns('Category', instance.organization_id)
    invalidate_cache_patterns(instance.organization_id, patterns)
