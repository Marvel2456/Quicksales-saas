"""
Cache utilities for consistent cache key generation and cache management.
Usage:
    from ims.cache_utils import cache_org_dashboard, invalidate_org_dashboard
    
    # Cache dashboard data
    cache_org_dashboard(org_id, branch_id, data)
    
    # Get cached data
    data = get_cached_org_dashboard(org_id, branch_id)
    
    # Invalidate cache when data changes
    invalidate_org_dashboard(org_id, branch_id)
"""

from django.core.cache import cache
from ImsV3.settings import CACHE_TIMEOUTS


class CacheKeys:
    """Centralized cache key definitions"""
    
    # Dashboard caching
    ORG_DASHBOARD = 'dashboard:org:{org_id}:branch:{branch_id}'
    ORG_BRANCH_SUMMARY = 'summary:org:{org_id}:branch:{branch_id}:date:{date}'
    
    # Sales caching
    SALES_LIST = 'sales:org:{org_id}:branch:{branch_id}:page:{page}'
    SALES_SUMMARY = 'sales_summary:org:{org_id}:period:{period}'
    
    # Inventory caching
    INVENTORY_LIST = 'inventory:org:{org_id}:branch:{branch_id}'
    INVENTORY_LOW_STOCK = 'inventory_low:org:{org_id}:branch:{branch_id}'
    
    # Product caching
    PRODUCT_LIST = 'products:org:{org_id}:category:{category_id}'
    PRODUCT_DETAIL = 'product:id:{product_id}'
    
    # User/Organization caching
    ORG_SETTINGS = 'org_settings:id:{org_id}'
    USER_PROFILE = 'user_profile:id:{user_id}'
    
    # Subscription caching
    SUBSCRIPTION_ACTIVE = 'subscription:org:{org_id}:active'
    
    # Notification caching
    USER_NOTIFICATIONS = 'notifications:user:{user_id}:unread'


def get_cache_key(template, **kwargs):
    """Generate cache key from template"""
    return template.format(**kwargs)


# ============================================================================
# Dashboard Caching
# ============================================================================

def cache_org_dashboard(org_id, branch_id, data):
    """Cache organization dashboard data"""
    key = get_cache_key(CacheKeys.ORG_DASHBOARD, org_id=org_id, branch_id=branch_id)
    cache.set(key, data, CACHE_TIMEOUTS.get('dashboard', 120))


def get_cached_org_dashboard(org_id, branch_id):
    """Get cached dashboard data"""
    key = get_cache_key(CacheKeys.ORG_DASHBOARD, org_id=org_id, branch_id=branch_id)
    return cache.get(key)


def invalidate_org_dashboard(org_id, branch_id=None):
    """Invalidate dashboard cache for organization"""
    if branch_id:
        key = get_cache_key(CacheKeys.ORG_DASHBOARD, org_id=org_id, branch_id=branch_id)
        cache.delete(key)
    else:
        # Invalidate all branches for org
        pattern = f'dashboard:org:{org_id}:*'
        cache.delete_pattern(pattern)


# ============================================================================
# Sales Caching
# ============================================================================

def cache_sales_list(org_id, branch_id, page, data):
    """Cache sales list"""
    key = get_cache_key(CacheKeys.SALES_LIST, org_id=org_id, branch_id=branch_id, page=page)
    cache.set(key, data, CACHE_TIMEOUTS.get('dashboard', 120))


def get_cached_sales_list(org_id, branch_id, page):
    """Get cached sales list"""
    key = get_cache_key(CacheKeys.SALES_LIST, org_id=org_id, branch_id=branch_id, page=page)
    return cache.get(key)


def invalidate_sales_list(org_id, branch_id=None):
    """Invalidate sales list cache"""
    if branch_id:
        pattern = f'sales:org:{org_id}:branch:{branch_id}:*'
    else:
        pattern = f'sales:org:{org_id}:*'
    cache.delete_pattern(pattern)


def cache_sales_summary(org_id, period, data):
    """Cache sales summary (daily, weekly, monthly)"""
    key = get_cache_key(CacheKeys.SALES_SUMMARY, org_id=org_id, period=period)
    cache.set(key, data, CACHE_TIMEOUTS.get('sales_summary', 60))


def invalidate_sales_summary(org_id):
    """Invalidate sales summary cache"""
    pattern = f'sales_summary:org:{org_id}:*'
    cache.delete_pattern(pattern)


# ============================================================================
# Inventory Caching
# ============================================================================

def cache_inventory_list(org_id, branch_id, data):
    """Cache inventory list"""
    key = get_cache_key(CacheKeys.INVENTORY_LIST, org_id=org_id, branch_id=branch_id)
    cache.set(key, data, CACHE_TIMEOUTS.get('inventory', 300))


def get_cached_inventory_list(org_id, branch_id):
    """Get cached inventory list"""
    key = get_cache_key(CacheKeys.INVENTORY_LIST, org_id=org_id, branch_id=branch_id)
    return cache.get(key)


def invalidate_inventory_list(org_id, branch_id=None):
    """Invalidate inventory list cache"""
    if branch_id:
        key = get_cache_key(CacheKeys.INVENTORY_LIST, org_id=org_id, branch_id=branch_id)
        cache.delete(key)
    else:
        pattern = f'inventory:org:{org_id}:*'
        cache.delete_pattern(pattern)


def cache_low_stock(org_id, branch_id, data):
    """Cache low stock items"""
    key = get_cache_key(CacheKeys.INVENTORY_LOW_STOCK, org_id=org_id, branch_id=branch_id)
    cache.set(key, data, CACHE_TIMEOUTS.get('inventory', 300))


def invalidate_low_stock(org_id, branch_id=None):
    """Invalidate low stock cache"""
    if branch_id:
        key = get_cache_key(CacheKeys.INVENTORY_LOW_STOCK, org_id=org_id, branch_id=branch_id)
        cache.delete(key)
    else:
        pattern = f'inventory_low:org:{org_id}:*'
        cache.delete_pattern(pattern)


# ============================================================================
# Product Caching
# ============================================================================

def cache_product_list(org_id, category_id, data):
    """Cache product list"""
    key = get_cache_key(CacheKeys.PRODUCT_LIST, org_id=org_id, category_id=category_id)
    cache.set(key, data, CACHE_TIMEOUTS.get('organization', 600))


def get_cached_product_list(org_id, category_id):
    """Get cached product list"""
    key = get_cache_key(CacheKeys.PRODUCT_LIST, org_id=org_id, category_id=category_id)
    return cache.get(key)


def cache_product_detail(product_id, data):
    """Cache product detail"""
    key = get_cache_key(CacheKeys.PRODUCT_DETAIL, product_id=product_id)
    cache.set(key, data, CACHE_TIMEOUTS.get('organization', 600))


def get_cached_product_detail(product_id):
    """Get cached product detail"""
    key = get_cache_key(CacheKeys.PRODUCT_DETAIL, product_id=product_id)
    return cache.get(key)


def invalidate_product_cache(org_id):
    """Invalidate all product caches for organization"""
    pattern = f'products:org:{org_id}:*'
    cache.delete_pattern(pattern)


# ============================================================================
# User/Organization Caching
# ============================================================================

def cache_org_settings(org_id, data):
    """Cache organization settings"""
    key = get_cache_key(CacheKeys.ORG_SETTINGS, org_id=org_id)
    cache.set(key, data, CACHE_TIMEOUTS.get('organization', 600))


def get_cached_org_settings(org_id):
    """Get cached organization settings"""
    key = get_cache_key(CacheKeys.ORG_SETTINGS, org_id=org_id)
    return cache.get(key)


def invalidate_org_settings(org_id):
    """Invalidate organization settings cache"""
    key = get_cache_key(CacheKeys.ORG_SETTINGS, org_id=org_id)
    cache.delete(key)


def cache_user_profile(user_id, data):
    """Cache user profile"""
    key = get_cache_key(CacheKeys.USER_PROFILE, user_id=user_id)
    cache.set(key, data, CACHE_TIMEOUTS.get('user_profile', 300))


def get_cached_user_profile(user_id):
    """Get cached user profile"""
    key = get_cache_key(CacheKeys.USER_PROFILE, user_id=user_id)
    return cache.get(key)


def invalidate_user_profile(user_id):
    """Invalidate user profile cache"""
    key = get_cache_key(CacheKeys.USER_PROFILE, user_id=user_id)
    cache.delete(key)


# ============================================================================
# Subscription Caching
# ============================================================================

def cache_active_subscription(org_id, data):
    """Cache active subscription"""
    key = get_cache_key(CacheKeys.SUBSCRIPTION_ACTIVE, org_id=org_id)
    cache.set(key, data, CACHE_TIMEOUTS.get('subscription', 1800))


def get_cached_active_subscription(org_id):
    """Get cached active subscription"""
    key = get_cache_key(CacheKeys.SUBSCRIPTION_ACTIVE, org_id=org_id)
    return cache.get(key)


def invalidate_subscription(org_id):
    """Invalidate subscription cache"""
    key = get_cache_key(CacheKeys.SUBSCRIPTION_ACTIVE, org_id=org_id)
    cache.delete(key)


# ============================================================================
# Notification Caching
# ============================================================================

def cache_user_notifications(user_id, count):
    """Cache unread notification count"""
    key = get_cache_key(CacheKeys.USER_NOTIFICATIONS, user_id=user_id)
    cache.set(key, count, CACHE_TIMEOUTS.get('user_profile', 300))


def get_cached_notification_count(user_id):
    """Get cached unread notification count"""
    key = get_cache_key(CacheKeys.USER_NOTIFICATIONS, user_id=user_id)
    return cache.get(key)


def invalidate_user_notifications(user_id):
    """Invalidate user notifications cache"""
    key = get_cache_key(CacheKeys.USER_NOTIFICATIONS, user_id=user_id)
    cache.delete(key)


# ============================================================================
# Batch Cache Operations
# ============================================================================

def invalidate_org_all_caches(org_id):
    """Invalidate all caches related to an organization"""
    patterns = [
        f'dashboard:org:{org_id}:*',
        f'sales:org:{org_id}:*',
        f'sales_summary:org:{org_id}:*',
        f'inventory:org:{org_id}:*',
        f'inventory_low:org:{org_id}:*',
        f'products:org:{org_id}:*',
        f'org_settings:id:{org_id}',
        f'subscription:org:{org_id}:*',
    ]
    for pattern in patterns:
        cache.delete_pattern(pattern)


def invalidate_branch_all_caches(org_id, branch_id):
    """Invalidate all caches related to a branch"""
    patterns = [
        f'dashboard:org:{org_id}:branch:{branch_id}*',
        f'sales:org:{org_id}:branch:{branch_id}:*',
        f'inventory:org:{org_id}:branch:{branch_id}',
        f'inventory_low:org:{org_id}:branch:{branch_id}',
    ]
    for pattern in patterns:
        cache.delete_pattern(pattern)


# ============================================================================
# Cache Statistics
# ============================================================================

def get_cache_stats():
    """Get Redis cache statistics"""
    from django.core.cache import cache
    try:
        # Works with redis backend
        info = cache._cache.get_client().info()
        return {
            'used_memory': info.get('used_memory_human'),
            'total_keys': info.get('db0', {}).get('keys', 0),
            'hit_rate': f"{(info.get('keyspace_hits', 0) / (info.get('keyspace_hits', 0) + info.get('keyspace_misses', 1))) * 100:.2f}%",
        }
    except Exception as e:
        return {'error': str(e)}
