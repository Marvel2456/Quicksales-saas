# Security Configuration Guide - Quick Fixes

## Apply These Settings to ImsV3/settings.py for Production

### 1. CSRF Cookie Security (Priority: HIGH)

Add to your production security settings:

```python
if ENV == 'production':
    # ... existing settings ...
    
    # CSRF Cookie Security
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True  # ADD THIS
    CSRF_COOKIE_SAMESITE = 'Strict'  # ADD THIS
    
    # Session Cookie Security
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True  # ADD THIS
    SESSION_COOKIE_SAMESITE = 'Strict'  # ADD THIS
```

**Why:** 
- `HTTPONLY`: Prevents JavaScript from accessing cookies (XSS protection)
- `SAMESITE = 'Strict'`: Prevents cookies from being sent in cross-site requests

---

### 2. HTTP Strict Transport Security (Priority: HIGH)

Add HSTS headers:

```python
if ENV == 'production':
    # ... existing settings ...
    
    # HTTP Strict Transport Security
    SECURE_HSTS_SECONDS = 31536000  # 1 year in seconds
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
```

**Why:** Forces all connections to use HTTPS, preventing man-in-the-middle attacks

---

### 3. Content Security Policy (Priority: MEDIUM)

```python
if ENV == 'production':
    # Content Security Policy
    SECURE_CONTENT_SECURITY_POLICY = {
        'default-src': ("'self'",),
        'script-src': (
            "'self'",
            "js.paystack.co",  # Paystack inline scripts
            "'unsafe-inline'",  # Only if needed for inline styles
        ),
        'style-src': ("'self'", "'unsafe-inline'"),
        'img-src': ("'self'", "data:", "https:"),
        'font-src': ("'self'",),
        'connect-src': ("'self'", "*.paystack.co"),
        'frame-ancestors': ("'self'",),
        'base-uri': ("'self'",),
        'form-action': ("'self'",),
    }
```

---

### 4. Database SSL Connection (Priority: HIGH)

```python
if ENV == 'production':
    DATABASES['default']['OPTIONS'] = {
        'sslmode': 'require',  # Require SSL for database connections
    }
```

---

### 5. Rate Limiting Middleware (Priority: MEDIUM)

Install the package:
```bash
pip install django-ratelimit
```

Then add to settings:

```python
# In MIDDLEWARE
MIDDLEWARE = [
    # ... existing middleware ...
    'django_ratelimit.middleware.RatelimitMiddleware',
]

# Rate limiting settings
RATELIMIT_ENABLE = ENV == 'production'
RATELIMIT_VIEW = '10/h'  # 10 requests per hour by default
```

Apply to payment endpoint:

```python
# In subscriptions/views.py
from django_ratelimit.decorators import ratelimit

@ratelimit(key='user', rate='5/h', method='POST')  # 5 payments per hour per user
def create_payment(request):
    # ... payment logic ...
    pass
```

---

### 6. Security Headers Middleware (Priority: MEDIUM)

Add middleware:

```python
# django-csp for Content Security Policy headers
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',  # Should be first
    # ... other middleware ...
]

# Additional security headers
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', cast=bool, default=True) if ENV == 'production' else False
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
REFERRER_POLICY = 'strict-origin-when-cross-origin'
```

---

### 7. Logging Configuration (Priority: MEDIUM)

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/django/security.log',
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'payment_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/django/payments.log',
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django.security': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
        'subscriptions.payments': {
            'handlers': ['payment_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

---

### 8. Secret Key Configuration (Priority: CRITICAL)

Ensure your SECRET_KEY is strong:

```python
import os
from django.core.management.utils import get_random_secret_key

# Generate with: python manage.py shell
# >>> from django.core.management.utils import get_random_secret_key
# >>> print(get_random_secret_key())

# Store in environment variable, not in code
SECRET_KEY = os.environ.get('SECRET_KEY', get_random_secret_key() if DEBUG else '')

if not SECRET_KEY and not DEBUG:
    raise ValueError("SECRET_KEY environment variable not set in production")
```

---

### 9. Complete Production Settings Block

Add this to your `ImsV3/settings.py`:

```python
# ============================================================================
# PRODUCTION SECURITY SETTINGS
# ============================================================================

if ENV == 'production':
    # SSL/HTTPS
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    
    # Database SSL
    DATABASES['default']['OPTIONS'] = {
        'sslmode': 'require',
    }
    
    # CSRF Security
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True
    CSRF_COOKIE_SAMESITE = 'Strict'
    
    # Session Security
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    
    # HSTS (HTTP Strict Transport Security)
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    
    # Security Headers
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'
    REFERRER_POLICY = 'strict-origin-when-cross-origin'
    
    # Content Security Policy
    SECURE_CONTENT_SECURITY_POLICY = {
        'default-src': ("'self'",),
        'script-src': ("'self'", "js.paystack.co"),
        'style-src': ("'self'", "'unsafe-inline'"),
        'img-src': ("'self'", "data:", "https:"),
        'font-src': ("'self'",),
        'connect-src': ("'self'", "*.paystack.co"),
        'frame-ancestors': ("'self'",),
        'form-action': ("'self'",),
    }
    
    # Secret Key
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable must be set in production")
    
    # Debug
    DEBUG = False

else:  # Development
    SECURE_SSL_REDIRECT = False
```

---

## Implementation Checklist

- [ ] Add CSRF_COOKIE_HTTPONLY and CSRF_COOKIE_SAMESITE
- [ ] Add SESSION_COOKIE_HTTPONLY and SESSION_COOKIE_SAMESITE
- [ ] Configure SECURE_HSTS_SECONDS
- [ ] Add database SSL requirement
- [ ] Set strong SECRET_KEY via environment variable
- [ ] Configure Content Security Policy
- [ ] Enable rate limiting for payment endpoints
- [ ] Set up logging for security events
- [ ] Add security headers via middleware
- [ ] Test with `python manage.py check --deploy`
- [ ] Run security audit tests again
- [ ] Deploy to production with these settings

---

## Verification Commands

After applying these settings, run:

```bash
# Check security configuration
docker-compose exec web python manage.py check --deploy

# Test CSRF protection
docker-compose exec web python manage.py test account.tests.CSRFSecurityTest

# Review security headers
curl -I https://your-domain.com

# Check Django security headers
curl -I https://your-domain.com | grep -i "strict-transport-security\|x-content-type-options\|x-frame-options"
```

---

## Production Environment Variables

Set these in your `.env` file or deployment platform:

```bash
# .env (add to your environment)
SECRET_KEY=<generate-with-get_random_secret_key()>
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
ENV=production
DEBUG=False
```

---

## References

- [Django Security Middleware](https://docs.djangoproject.com/en/4.2/ref/middleware/#django.middleware.security.SecurityMiddleware)
- [OWASP CSP Guide](https://owasp.org/www-community/attacks/xss/)
- [HTTP Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security)
- [CSRF Protection in Django](https://docs.djangoproject.com/en/4.2/middleware/csrf/)
