from django.shortcuts import render
from subscriptions.models import Plan

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

