from django.shortcuts import render, redirect
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
    # Redirect to the latest GitHub Release page so users can select their architecture (x64/ARM)
    return redirect("https://github.com/Marvel2456/Quicksales-saas/releases/latest")

def download_mac(request):
    DesktopDownload.objects.create(
        platform='mac',
        ip_address=get_client_ip(request)
    )
    # Redirect to the latest GitHub Release page so users can select their architecture (x64/aarch64)
    return redirect("https://github.com/Marvel2456/Quicksales-saas/releases/latest")

# Create your views here.


def landingPage(request):
    # Get tier and size choices from the Plan model
    tier_choices = Plan.TIER_CHOICES
    size_choices = Plan.SIZE_CHOICES
    
    # Get all plans except the free tier for display on landing page
    plans = Plan.objects.exclude(tier='free').order_by('tier', 'size', 'billing_frequency')
    
    # Get specific starter plans for the pricing section (Monthly)
    starter_plans = Plan.objects.filter(
        size='starter', 
        billing_frequency='monthly'
    ).exclude(tier='free').order_by('price')

    context = {
        'tier_choices': tier_choices,
        'size_choices': size_choices,
        'plans': plans,
        'starter_plans': starter_plans,
    }
    return render(request, 'pages/landing_page.html', context)

