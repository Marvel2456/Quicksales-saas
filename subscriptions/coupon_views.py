"""Views for coupon management and validation"""
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from account.decorators import role_required
from .models import Plan, Coupon, CouponRedemption
from decimal import Decimal
import json


@csrf_exempt
@require_POST
def validate_coupon_api(request):
    """API endpoint to validate coupon code and calculate discount"""
    try:
        data = json.loads(request.body)
        coupon_code = data.get("coupon_code", "").strip()
        plan_price = data.get("plan_price")
        
        if not coupon_code:
            return JsonResponse({"error": "Missing coupon code"}, status=400)
        
        # Use the provided plan price, or default if not provided
        if plan_price:
            plan_price = float(plan_price)
        else:
            plan_price = 50000  # Default base price for validation
        
        # Get organization if user is authenticated, otherwise validate coupon generally
        organization = None
        if request.user and request.user.is_authenticated:
            organization = getattr(request.user, 'organization', None)
        
        try:
            coupon = Coupon.objects.get(code__iexact=coupon_code)
        except Coupon.DoesNotExist:
            return JsonResponse({
                "success": False,
                "message": "Invalid coupon code",
                "original_amount": plan_price,
            }, status=400)

        if not coupon.is_valid():
            return JsonResponse({
                "success": False,
                "message": "Coupon is no longer valid",
                "original_amount": plan_price,
            }, status=400)

        if coupon.uses >= coupon.max_uses:
            return JsonResponse({
                "success": False,
                "message": "Coupon has reached maximum uses",
                "original_amount": plan_price,
            }, status=400)

        # Check if organization already used this coupon (only if user is authenticated)
        if organization and CouponRedemption.objects.filter(coupon=coupon, organization=organization).exists():
            return JsonResponse({
                "success": False,
                "message": "You have already used this coupon",
                "original_amount": plan_price,
            }, status=400)

        # Calculate discount
        original_amount = Decimal(str(plan_price))
        coupon_value = Decimal(str(coupon.value))
        
        if coupon.type == 'percent':
            discount = (original_amount * coupon_value) / Decimal('100')
            final_amount = original_amount - discount
        elif coupon.type == 'fixed':
            discount = coupon_value
            final_amount = max(original_amount - discount, Decimal('0.00'))
        elif coupon.type == 'free_month':
            discount = original_amount
            final_amount = Decimal('0.00')
        else:
            return JsonResponse({
                "error": "Invalid coupon type",
            }, status=500)

        return JsonResponse({
            "success": True,
            "message": "Coupon applied successfully",
            "original_amount": float(original_amount),
            "discount": float(discount),
            "final_amount": float(final_amount),
            "coupon_type": coupon.type,
            "coupon_id": str(coupon.id),
        })
    
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Coupon validation error: {error_trace}")
        return JsonResponse({"error": str(e), "trace": error_trace}, status=500)


@role_required(roles=['owner'])
@login_required
def apply_coupon_to_subscription(request, subscription_id):
    """Apply a coupon to an existing subscription"""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        from .models import Subscription
        
        data = json.loads(request.body)
        coupon_code = data.get("coupon_code", "").strip()
        
        if not coupon_code:
            return JsonResponse({"error": "Coupon code is required"}, status=400)
        
        subscription = get_object_or_404(
            Subscription,
            id=subscription_id,
            organization=request.user.organization
        )
        
        try:
            coupon = Coupon.objects.get(code__iexact=coupon_code)
        except Coupon.DoesNotExist:
            return JsonResponse({
                "success": False,
                "message": "Invalid coupon code",
            }, status=400)

        if not coupon.is_valid():
            return JsonResponse({
                "success": False,
                "message": "Coupon is no longer valid",
            }, status=400)

        # Check if organization already used this coupon
        if CouponRedemption.objects.filter(coupon=coupon, organization=subscription.organization).exists():
            return JsonResponse({
                "success": False,
                "message": "You have already used this coupon",
            }, status=400)

        # Record coupon redemption
        redemption = CouponRedemption.objects.create(
            coupon=coupon,
            organization=subscription.organization,
            subscription=subscription,
        )
        
        # Increment coupon usage
        coupon.uses += 1
        coupon.save()
        
        return JsonResponse({
            "success": True,
            "message": "Coupon applied to subscription",
            "coupon_code": coupon.code,
        })
    
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
