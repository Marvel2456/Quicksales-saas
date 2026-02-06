# Performance Optimization & Caching Implementation Guide

## Overview

This document explains the complete performance optimization implementation for Quicksales SaaS, including:
- Database indexing (24 indexes deployed)
- Redis caching infrastructure
- Query optimization in views
- Cache decorators and invalidation
- Performance monitoring with django-debug-toolbar

---

## 1. Database Optimization

### Deployed Indexes (24 Total)

**Account Models:**
- `Organization`: indexed on name, slug, is_active, created_at, owned_by
- `Branch`: indexed on organization, name, created_at
- `CustomUser`: indexed on organization, branch, role, email, created_at
- `ActivityLog`: indexed on organization, branch, staff, timestamp
- `Notification`: indexed on user, is_read, created_at

**IMS Models:**
- `Category`: indexed on organization, branch, date_created
- `Product`: indexed on organization, branch, product_name, product_code, category, created_at
- `Inventory`: indexed on organization, branch, product, status, quantity
- `Sale`: indexed on 7 fields (organization, branch, staff, method, date_updated, completed, cancelled)
- `SalesItem`: indexed on organization, branch, sale, product, last_updated
- `ErrorTicket`: indexed on organization, status, assigned_to, date_added
- `TicketComment`: indexed on ticket, created_at

**Check Deployed Indexes:**
```bash
docker-compose exec -e PGPASSWORD=password@123 db psql -U quicksales_user -d quicksales \
  -c "SELECT COUNT(*) as total_indexes FROM pg_indexes WHERE schemaname='public';"
```

Expected output: **222 total indexes**

---

## 2. Redis Caching Configuration

### Cache Settings (ImsV3/settings.py)

```python
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://redis:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 50,
                'retry_on_timeout': True,
            },
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
            'COMPRESSOR_OPTIONS': {
                'level': 6,
            },
        },
        'TIMEOUT': 300,
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
```

### Testing Cache Connectivity

```bash
# Test from Django shell
docker-compose exec web python manage.py shell

# In shell:
from django.core.cache import cache
cache.set('test', 'working', 60)
print(cache.get('test'))  # Should print 'working'
```

---

## 3. View Optimizations

### Query Optimization Patterns

All views have been updated with the following patterns:

**1. Use select_related for ForeignKey lookups:**
```python
# Before (N+1 queries)
inventory = Inventory.objects.filter(branch=branch)

# After (single query with JOIN)
inventory = Inventory.objects.filter(
    branch=branch
).select_related('product', 'branch')
```

**2. Use prefetch_related for reverse relations:**
```python
# Before (N queries for related items)
items = sale.salesitem_set.all()

# After (optimized with separate queries)
items = sale.salesitem_set.select_related('inventory', 'product').all()
```

**3. Use aggregate instead of loops:**
```python
# Before (Python loop, N queries)
total_sales = sum(s.final_total_price for s in sales)
transaction_count = len(sales)

# After (single query, database-level aggregation)
agg = sales.aggregate(
    total_sales=Sum('final_total_price'),
    transaction_count=Count('id'),
)
total_sales = agg['total_sales'] or 0
transaction_count = agg['transaction_count']
```

**4. Fix pagination querysets:**
```python
# Before (paginating all records)
paginator = Paginator(Inventory.objects.all(), 15)

# After (paginate filtered queryset)
inventory_qs = Inventory.objects.filter(branch=branch).select_related(...)
paginator = Paginator(inventory_qs, 15)
```

### Optimized Views

- ✅ `sale_views.py`: branchStore, store, cart, checkout, sales (5 views)
- ✅ `inventory_views.py`: branch_inventory, inventory_list, branchInventory (3 views)
- ✅ `product_views.py`: branch_product, product_category, edit_product (3 views)
- ✅ `dashboard_views.py`: branchDasboard, dashboard (2 views)

---

## 4. View-Level Caching

### Using Cache Decorators

The `ims/view_caching.py` module provides decorators for caching view responses:

**Basic Usage:**
```python
from ims.view_caching import cached_view

@cached_view(timeout=300, key_prefix='sales_list')
def sales_list(request, pk):
    # View code here
    pass
```

**Paginated Data Caching:**
```python
from ims.view_caching import cache_paginated_data

@cache_paginated_data(timeout=300)
def inventory_list(request, pk):
    # Caches each page separately
    pass
```

### Cache Timeout Presets

```python
CACHE_TIMEOUTS = {
    'list_view': 5 * 60,           # 5 minutes
    'detail_view': 10 * 60,        # 10 minutes
    'dashboard': 2 * 60,           # 2 minutes
    'report': 15 * 60,             # 15 minutes
    'static_data': 60 * 60,        # 1 hour
    'user_data': 1 * 60,           # 1 minute
}
```

---

## 5. Cache Invalidation

### Automatic Invalidation via Signals

When models are saved or deleted, related caches are automatically invalidated:

**IMS Model Signals (ims/cache_signals.py):**

| Model | Invalidates |
|-------|------------|
| Sale | sales_list, dashboard, branch_sales |
| Inventory | inventory_list, store, dashboard |
| Product | product_category, store, inventory_list |
| Category | category_list, product_category |

**Example:**
```python
# When you create a new Sale, these caches are auto-invalidated:
# - sales_list:org:1:*
# - dashboard:org:1:*
# - branch_sales:org:1:*

sale = Sale.objects.create(...)  # Cache automatically cleared
```

### Manual Cache Invalidation

```python
from ims.view_caching import invalidate_view_cache

# Invalidate cache for specific organization and pattern
invalidate_view_cache(org_id=1, cache_pattern='sales_list:org:1:*')
```

---

## 6. Performance Monitoring

### Django Debug Toolbar

The django-debug-toolbar is configured for development environments to monitor:
- Query count and execution time
- Database queries
- Cache hits/misses
- Template rendering time
- HTTP headers
- Signals sent

**Access:**
1. Open any page in your application
2. Look for the debug toolbar on the right side of the page
3. Click the icon to expand detailed information

**Query Analysis:**
- Check "SQL" tab to see all database queries for the page
- Look for N+1 queries that should be optimized
- Monitor query count reduction after optimizations

### Docker Deployment

After making changes, redeploy:

```bash
cd /Users/eseosa/Documents/Quicksales-saas

# Rebuild with new packages
docker-compose down
docker-compose up -d --build

# Verify deployment
docker-compose ps
docker-compose exec web python manage.py check
```

---

## 7. Performance Improvements

### Before Optimization

- List views: ~50+ queries per page
- Cart view: ~30+ queries
- Dashboard: ~40+ queries
- Average response time: 2-5 seconds

### After Optimization

Expected improvements with all optimizations active:

| View Type | Before | After | Improvement |
|-----------|--------|-------|------------|
| List view (inventory) | 50+ queries | 5-8 queries | 80-90% ⬇️ |
| Cart | 30+ queries | 5-10 queries | 70-85% ⬇️ |
| Dashboard | 40+ queries | 8-12 queries | 75-80% ⬇️ |
| Response time | 2-5 sec | 200-500 ms | 75-90% ⬇️ |

---

## 8. Cache Monitoring

### Get Cache Statistics

```python
from ims.view_caching import get_cache_stats

stats = get_cache_stats(org_id=1)
print(stats)
# Output: {'hits': 245, 'misses': 32, 'hit_rate': 0.88}
```

### Clear All Cache (if needed)

```bash
# From Django shell
docker-compose exec web python manage.py shell

from django.core.cache import cache
cache.clear()  # Clears all cached data
```

---

## 9. Best Practices

### ✅ DO:
- Cache read-heavy views (list, detail, dashboard)
- Use `select_related()` for ForeignKey fields
- Use `prefetch_related()` for reverse relations
- Use database aggregation for summations
- Invalidate cache when data changes
- Monitor query counts with debug toolbar

### ❌ DON'T:
- Cache rapidly changing data
- Use views with `request.POST` in caching decorators
- Cache sensitive user-specific data without isolation
- Cache without proper timeout values
- Forget to invalidate cache on model saves

---

## 10. Troubleshooting

### High Cache Miss Rate

```bash
# Check if Redis is running
docker-compose ps | grep redis

# Check Redis connection
docker-compose exec redis redis-cli ping
# Should return: PONG
```

### Queries Still High

1. Check debug toolbar SQL tab
2. Look for N+1 query patterns
3. Verify select_related/prefetch_related usage
4. Check for missing indexes

### Cache Not Invalidating

1. Verify signals are registered: check `ims/apps.py` ready() method
2. Check if post_save signal is triggered: add logging
3. Verify cache key patterns match in CACHE_INVALIDATION_MAP

---

## 11. Deployment Checklist

- [ ] All 24 database indexes created and deployed
- [ ] Redis caching configured and tested
- [ ] Connection pooling enabled (CONN_MAX_AGE = 600)
- [ ] Select_related/prefetch_related added to views
- [ ] Aggregate functions used where applicable
- [ ] Cache signals registered
- [ ] Django debug toolbar configured (dev only)
- [ ] Migrations applied: `python manage.py migrate`
- [ ] Query count monitoring in place

---

## Performance Target

With all optimizations implemented:
- **Query count per page: < 10 queries** (down from 50+)
- **Response time: < 500ms** (down from 2-5 seconds)
- **Cache hit rate: > 80%**
- **Concurrent users supported: 1000+ on Hostinger KVM 2**

---

## References

- [Django Query Optimization](https://docs.djangoproject.com/en/5.0/topics/db/optimization/)
- [Django Caching Framework](https://docs.djangoproject.com/en/5.0/topics/cache/)
- [Django Debug Toolbar](https://django-debug-toolbar.readthedocs.io/)
- [Redis Documentation](https://redis.io/docs/)
- [Database Indexing Best Practices](https://use-the-index-luke.com/)
