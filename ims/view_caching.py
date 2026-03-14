"""
View Caching Utilities for Quicksales SaaS
============================================

This module provides caching decorators and utilities for high-traffic views.
Implements page caching, query result caching, and cache invalidation strategies.

Key Features:
- @cache_page and @cache_result decorators for view-level caching
- Organization-specific cache keys
- Cache invalidation hooks
- Performance monitoring utilities
"""

from django.views.decorators.cache import cache_page
from django.core.cache import cache
from django.utils.decorators import decorator_from_middleware_with_args
from django.conf import settings
from functools import wraps
from django.http import HttpRequest
from datetime import timedelta
import hashlib
import json


# Cache timeout constants (in seconds)
CACHE_TIMEOUTS = {
    'list_view': 5 * 60,           # 5 minutes for list views
    'detail_view': 10 * 60,        # 10 minutes for detail views
    'dashboard': 2 * 60,           # 2 minutes for dashboards
    'report': 15 * 60,             # 15 minutes for reports
    'static_data': 60 * 60,        # 1 hour for static data (categories, etc.)
    'user_data': 1 * 60,           # 1 minute for user-specific data
}


def get_organization_cache_key(request, key_prefix, *args, **kwargs):
    """
    Generate an organization-specific cache key that includes view arguments
    
    Args:
        request: Django request object
        key_prefix: Prefix for the cache key
        *args: Variable positional arguments from the view
        **kwargs: Variable keyword arguments from the view (e.g., pk/branch_id)
    
    Returns:
        Organization-specific cache key string
    """
    org_id = getattr(request.user, 'organization_id', 'anonymous')
    user_id = getattr(request.user, 'id', 'anonymous')
    
    # Include query parameters in cache key for filtered views
    query_string = request.GET.urlencode()
    query_hash = hashlib.md5(query_string.encode()).hexdigest()[:8] if query_string else 'no-filter'
    
    # Include view arguments and keyword arguments (like branch pk) in cache key
    args_str = str(args) if args else ''
    kwargs_str = str(kwargs) if kwargs else ''
    args_hash = hashlib.md5(f"{args_str}:{kwargs_str}".encode()).hexdigest()[:8] if args_str or kwargs_str else 'no-params'
    
    return f"{key_prefix}:org:{org_id}:user:{user_id}:params:{args_hash}:query:{query_hash}"


def cached_view(timeout=300, key_prefix=None):
    """
    Decorator for caching view responses based on organization and user
    
    Args:
        timeout: Cache timeout in seconds (default: 5 minutes)
        key_prefix: Custom cache key prefix
    
    Usage:
        @cached_view(timeout=600, key_prefix='sales_list')
        def sales_list_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Disable caching in development to avoid stale templates/assets
            if getattr(settings, 'ENV', 'development') == 'development':
                return view_func(request, *args, **kwargs)
            # Don't cache if user is not authenticated or request has specific parameters
            if not request.user.is_authenticated:
                return view_func(request, *args, **kwargs)
            
            # Skip cache for POST requests
            if request.method != 'GET':
                return view_func(request, *args, **kwargs)
            
            prefix = key_prefix or view_func.__name__
            cache_key = get_organization_cache_key(request, prefix, *args, **kwargs)
            
            # Try to get from cache
            cached_response = cache.get(cache_key)
            if cached_response is not None:
                return cached_response
            
            # If not in cache, call view and cache result
            response = view_func(request, *args, **kwargs)
            cache.set(cache_key, response, timeout)
            
            return response
        
        return wrapper
    return decorator


def cache_paginated_data(timeout=300):
    """
    Decorator for caching paginated queryset data
    
    Usage:
        @cache_paginated_data(timeout=300)
        def list_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated or request.method != 'GET':
                return view_func(request, *args, **kwargs)
            
            # Create cache key including page number and view arguments
            page = request.GET.get('page', 1)
            cache_key = get_organization_cache_key(request, f"{view_func.__name__}:page:{page}", *args, **kwargs)
            
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return cached_data
            
            response = view_func(request, *args, **kwargs)
            cache.set(cache_key, response, timeout)
            
            return response
        
        return wrapper
    return decorator


class CacheInvalidationMixin:
    """
    Mixin for models to handle cache invalidation on save/delete
    
    Usage:
        class Sale(CacheInvalidationMixin, models.Model):
            def invalidate_cache_patterns(self):
                # Return list of cache key patterns to invalidate
                return [
                    f"sales_list:org:{self.organization_id}:*",
                    f"sales_detail:org:{self.organization_id}:sale:{self.id}",
                ]
    """
    
    def invalidate_related_caches(self):
        """Override this method in subclass to define cache patterns to invalidate"""
        pass
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.invalidate_related_caches()
    
    def delete(self, *args, **kwargs):
        self.invalidate_related_caches()
        super().delete(*args, **kwargs)


def invalidate_view_cache(org_id, cache_pattern):
    """
    Invalidate cache entries matching a pattern
    
    Args:
        org_id: Organization ID
        cache_pattern: Pattern to match (e.g., 'sales_list:org:1:*')
    """
    try:
        # Get all cache keys matching pattern
        keys_to_delete = []
        for key in cache.keys(f"{cache_pattern}"):
            keys_to_delete.append(key)
        
        if keys_to_delete:
            cache.delete_many(keys_to_delete)
    except Exception as e:
        # Logging in production
        print(f"Cache invalidation error: {e}")


def get_cache_stats(org_id):
    """
    Get cache statistics for an organization
    
    Returns:
        Dictionary with cache hit/miss statistics
    """
    stats_key = f"cache_stats:org:{org_id}"
    return cache.get(stats_key, {
        'hits': 0,
        'misses': 0,
        'hit_rate': 0.0,
    })


# Cache tag mappings for related model invalidation
CACHE_INVALIDATION_MAP = {
    'Sale': [
        'sales_list:org:*',
        'dashboard:org:*',
        'branch_sales:org:*',
    ],
    'Inventory': [
        'inventory_list:org:*',
        'store:org:*',
        'dashboard:org:*',
    ],
    'Product': [
        'product_category:org:*',
        'store:org:*',
        'inventory_list:org:*',
    ],
    'Category': [
        'category_list:org:*',
        'product_category:org:*',
    ],
}


def get_invalidation_patterns(model_name, org_id):
    """
    Get cache patterns to invalidate for a specific model change
    
    Args:
        model_name: Name of the model
        org_id: Organization ID
    
    Returns:
        List of cache patterns to invalidate
    """
    patterns = CACHE_INVALIDATION_MAP.get(model_name, [])
    return [p.replace('*', str(org_id)) for p in patterns]
