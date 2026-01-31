from django.shortcuts import render
from subscriptions.models import Plan

# Create your views here.


def landingPage(request):
    # Get tier and size choices from the Plan model
    tier_choices = Plan.TIER_CHOICES
    size_choices = Plan.SIZE_CHOICES
    
    # Get all plans except the free tier for display on landing page
    plans = Plan.objects.exclude(tier='free').order_by('tier', 'size', 'billing_frequency')
    
    context = {
        'tier_choices': tier_choices,
        'size_choices': size_choices,
        'plans': plans,
    }
    return render(request, 'pages/landing_page.html', context)

