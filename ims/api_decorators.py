import functools
from django.http import JsonResponse
from django.utils import timezone
from ims.models import APIKey
from subscriptions.models import Subscription

def require_api_key(view_func):
    @functools.wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        # 1. Extract API Key from headers
        api_key_str = request.headers.get('X-API-Key')
        if not api_key_str:
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                api_key_str = auth_header.split(' ')[1]

        if not api_key_str:
            return JsonResponse({'error': 'Authentication credentials were not provided. Use X-API-Key header or Authorization: Bearer <key>'}, status=401)

        # 2. Lookup API Key in database
        try:
            api_key = APIKey.objects.select_related('organization').get(key=api_key_str)
        except APIKey.DoesNotExist:
            return JsonResponse({'error': 'Invalid API Key'}, status=401)

        if not api_key.is_active:
            return JsonResponse({'error': 'API Key is inactive or revoked'}, status=401)

        # 3. Validate Organization Subscription Status (Bypassed for Developer Sandbox accounts)
        if api_key.organization.business_type != 'developer':
            subscription = Subscription.objects.filter(organization=api_key.organization, is_active=True).first()
            if not subscription or subscription.end_date < timezone.now():
                return JsonResponse({'error': 'Active subscription is required to access the API'}, status=403)

        # 4. Attach contexts to request
        request.api_organization = api_key.organization
        
        # Track last used time
        api_key.last_used_at = timezone.now()
        api_key.save(update_fields=['last_used_at'])

        return view_func(request, *args, **kwargs)
    return wrapped_view
