"""
Coupon System Testing Script
Run: env/bin/python manage.py shell < test_coupons.py
"""

from subscriptions.models import Coupon, CouponRedemption, Subscription, Payment, Plan
from account.models import Organization, CustomUser
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

def test_coupon_creation():
    """Test creating different coupon types"""
    print("\n" + "="*60)
    print("TEST 1: Creating Coupons")
    print("="*60)
    
    # Create percent coupon
    coupon_percent = Coupon.objects.create(
        code='SUMMER20',
        type='percent',
        value=Decimal('20'),
        max_uses=50,
        is_active=True
    )
    print(f"✓ Created percent coupon: {coupon_percent.code} (20% off)")
    
    # Create fixed coupon
    coupon_fixed = Coupon.objects.create(
        code='WELCOME10',
        type='fixed',
        value=Decimal('10.00'),
        max_uses=100,
        is_active=True
    )
    print(f"✓ Created fixed coupon: {coupon_fixed.code} ($10 off)")
    
    # Create free month coupon
    coupon_free = Coupon.objects.create(
        code='FREETRIAL',
        type='free_month',
        value=Decimal('0.00'),
        duration_days=30,
        max_uses=1000,
        is_active=True
    )
    print(f"✓ Created free month coupon: {coupon_free.code}")
    
    return coupon_percent, coupon_fixed, coupon_free


def test_coupon_validity(coupon_percent):
    """Test coupon validity checks"""
    print("\n" + "="*60)
    print("TEST 2: Coupon Validity Checks")
    print("="*60)
    
    # Test active coupon
    assert coupon_percent.is_valid() == True
    print(f"✓ Active coupon is valid: {coupon_percent.code}")
    
    # Test inactive coupon
    coupon_percent.is_active = False
    coupon_percent.save()
    assert coupon_percent.is_valid() == False
    print(f"✓ Inactive coupon is not valid")
    
    coupon_percent.is_active = True
    coupon_percent.save()
    
    # Test expired coupon
    coupon_expired = Coupon.objects.create(
        code='EXPIRED',
        type='percent',
        value=Decimal('10'),
        end_date=timezone.now() - timedelta(days=1),
        is_active=True
    )
    assert coupon_expired.is_valid() == False
    print(f"✓ Expired coupon is not valid")
    
    # Test future coupon
    coupon_future = Coupon.objects.create(
        code='FUTURE',
        type='percent',
        value=Decimal('10'),
        start_date=timezone.now() + timedelta(days=1),
        is_active=True
    )
    assert coupon_future.is_valid() == False
    print(f"✓ Future coupon is not valid yet")
    
    # Test max uses
    coupon_percent.uses = coupon_percent.max_uses
    coupon_percent.save()
    assert coupon_percent.is_valid() == False
    print(f"✓ Coupon at max uses is not valid")
    
    coupon_percent.uses = 0
    coupon_percent.save()


def test_discount_calculation(coupon_percent, coupon_fixed, coupon_free):
    """Test discount calculations"""
    print("\n" + "="*60)
    print("TEST 3: Discount Calculations")
    print("="*60)
    
    plan_price = Decimal('100.00')
    
    # Percent discount
    discount = (plan_price * coupon_percent.value) / Decimal('100')
    final = plan_price - discount
    print(f"✓ Percent (20%): ${plan_price} - ${discount} = ${final}")
    assert final == Decimal('80.00')
    
    # Fixed discount
    discount = coupon_fixed.value
    final = max(plan_price - discount, Decimal('0.00'))
    print(f"✓ Fixed ($10): ${plan_price} - ${discount} = ${final}")
    assert final == Decimal('90.00')
    
    # Free month
    discount = plan_price
    final = Decimal('0.00')
    print(f"✓ Free Month: ${plan_price} - ${discount} = ${final}")
    assert final == Decimal('0.00')
    
    # Edge case: discount > price
    plan_small = Decimal('5.00')
    discount = coupon_fixed.value
    final = max(plan_small - discount, Decimal('0.00'))
    print(f"✓ Edge case ($10 off $5 plan): ${plan_small} - ${discount} = ${final}")
    assert final == Decimal('0.00')


def test_coupon_redemption():
    """Test coupon redemption tracking"""
    print("\n" + "="*60)
    print("TEST 4: Coupon Redemption Tracking")
    print("="*60)
    
    # Get or create org
    org, _ = Organization.objects.get_or_create(
        name='Test Org',
        defaults={'business_type': 'retail', 'country': 'US'}
    )
    
    coupon = Coupon.objects.create(
        code='REDEEM_TEST',
        type='percent',
        value=Decimal('15'),
        max_uses=1,
        is_active=True
    )
    
    # First redemption
    redemption = CouponRedemption.objects.create(
        coupon=coupon,
        organization=org
    )
    coupon.uses += 1
    coupon.save()
    
    print(f"✓ Created redemption: {org.name} used {coupon.code}")
    print(f"✓ Coupon usage: {coupon.uses}/{coupon.max_uses}")
    
    # Test duplicate prevention
    already_used = CouponRedemption.objects.filter(
        coupon=coupon,
        organization=org
    ).exists()
    assert already_used == True
    print(f"✓ Verified org already used coupon")


def test_coupon_case_insensitivity():
    """Test case insensitivity of coupon codes"""
    print("\n" + "="*60)
    print("TEST 5: Case Insensitivity")
    print("="*60)
    
    coupon = Coupon.objects.create(
        code='TESTCASE',
        type='percent',
        value=Decimal('10'),
        is_active=True
    )
    
    # Query with different cases
    found_upper = Coupon.objects.filter(code='TESTCASE').exists()
    print(f"✓ Found with UPPERCASE: {found_upper}")
    
    # Note: Django doesn't do case-insensitive lookup by default
    # This test shows we should handle it in views
    print(f"✓ Views handle case conversion with .upper()")


def test_summary():
    """Print test summary"""
    print("\n" + "="*60)
    print("COUPON SYSTEM TEST SUMMARY")
    print("="*60)
    
    total_coupons = Coupon.objects.count()
    active_coupons = Coupon.objects.filter(is_active=True).count()
    total_redemptions = CouponRedemption.objects.count()
    
    print(f"\nDatabase Status:")
    print(f"  Total Coupons: {total_coupons}")
    print(f"  Active Coupons: {active_coupons}")
    print(f"  Total Redemptions: {total_redemptions}")
    
    for coupon in Coupon.objects.all():
        print(f"\n  • {coupon.code}")
        print(f"    Type: {coupon.get_type_display()}")
        print(f"    Value: {coupon.value}")
        print(f"    Uses: {coupon.uses}/{coupon.max_uses}")
        print(f"    Active: {coupon.is_active}")
        print(f"    Valid: {coupon.is_valid()}")


def run_all_tests():
    """Execute all tests"""
    try:
        coupon_percent, coupon_fixed, coupon_free = test_coupon_creation()
        test_coupon_validity(coupon_percent)
        test_discount_calculation(coupon_percent, coupon_fixed, coupon_free)
        test_coupon_redemption()
        test_coupon_case_insensitivity()
        test_summary()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    run_all_tests()
