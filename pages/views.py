from django.shortcuts import render, redirect
from django.conf import settings
from django.core.cache import cache
import ipaddress
import requests
from subscriptions.models import Plan
from .models import DesktopDownload

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def download_windows(request):
    DesktopDownload.objects.create(
        platform='windows',
        ip_address=get_client_ip(request)
    )
    # Direct download link for the compiled Windows installer (MSI)
    version = getattr(settings, 'TAURI_APP_VERSION', '0.1.0')
    github_url = f"https://github.com/Marvel2456/Quicksales-saas/releases/latest/download/Quicksales_{version}_x64_en-US.msi"
    return redirect(github_url)

def download_mac(request):
    DesktopDownload.objects.create(
        platform='mac',
        ip_address=get_client_ip(request)
    )
    # Direct download link for the compiled macOS app disk image (DMG)
    version = getattr(settings, 'TAURI_APP_VERSION', '0.1.0')
    github_url = f"https://github.com/Marvel2456/Quicksales-saas/releases/latest/download/Quicksales_{version}_aarch64.dmg"
    return redirect(github_url)

# Create your views here.


def _detect_visitor_is_nigeria(request):
    """Detect whether the visitor is in Nigeria from CDN headers or IP geolocation (cached 24h)."""
    override = (request.GET.get('currency') or '').strip().upper()
    if override == 'USD':
        return False
    if override == 'NGN':
        return True

    for header in ('HTTP_CF_IPCOUNTRY', 'HTTP_X_VERCEL_IP_COUNTRY', 'HTTP_X_COUNTRY_CODE'):
        country_code = (request.META.get(header) or '').strip().upper()
        if country_code and country_code not in ('XX', 'T1'):
            return country_code == 'NG'

    ip = (get_client_ip(request) or '').strip()
    if not ip:
        return True

    try:
        ip_obj = ipaddress.ip_address(ip)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved:
            return True
    except ValueError:
        return True

    cache_key = f"geoip_country:{ip}"
    cached_code = cache.get(cache_key)
    if cached_code is not None:
        return cached_code == 'NG'

    try:
        resp = requests.get(f"https://ipapi.co/{ip}/country/", timeout=1.5)
        if resp.status_code == 200:
            code = resp.text.strip().upper()[:2]
            if code and code.isalpha():
                cache.set(cache_key, code, 60 * 60 * 24)
                return code == 'NG'
    except Exception:
        pass

    return True


def landingPage(request):
    # Get tier and size choices from the Plan model
    tier_choices = Plan.TIER_CHOICES
    size_choices = Plan.SIZE_CHOICES
    visitor_is_nigeria = _detect_visitor_is_nigeria(request)

    # Get all plans except the free tier for display on landing page
    plans = Plan.objects.exclude(tier='free').filter(show_on_landing=True).order_by('plan_category', 'tier', 'size', 'billing_frequency')

    # Standard Business starter plans (Monthly)
    starter_plans = Plan.objects.filter(
        plan_category='standard',
        size='starter',
        billing_frequency='monthly',
        show_on_landing=True,
    ).exclude(tier='free').order_by('price')

    # Online Vendor plans created in Django Admin
    online_vendor_plans = Plan.objects.filter(
        plan_category='online_vendor',
        show_on_landing=True,
    ).exclude(tier='free').order_by('price', 'created_at')

    context = {
        'tier_choices': tier_choices,
        'size_choices': size_choices,
        'plans': plans,
        'starter_plans': starter_plans,
        'online_vendor_plans': online_vendor_plans,
        'visitor_is_nigeria': visitor_is_nigeria,
        'currency_symbol': '₦' if visitor_is_nigeria else '$',
    }
    return render(request, 'pages/landing_page.html', context)

def api_docs(request):
    """
    Renders the API integration documentation page for developers.
    """
    return render(request, 'pages/api_docs.html')

