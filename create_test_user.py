from account.models import CustomUser, Organization, Branch
from subscriptions.models import Plan, Subscription
from django.utils import timezone
from datetime import timedelta

# Create organization
org = Organization.objects.create(
    name="Test Organization",
    business_type="grocery",
    country="Nigeria"
)

# Create branch
branch = Branch.objects.create(
    organization=org,
    name="Main Branch",
    address="123 Test Street"
)

# Create free plan if not exists
free_plan, _ = Plan.objects.get_or_create(
    tier='basic',
    size='starter',
    billing_frequency='monthly',
    defaults={'price': 0, 'duration_in_days': 30}
)

# Create subscription
sub = Subscription.objects.create(
    organization=org,
    plan=free_plan,
    start_date=timezone.now(),
    end_date=timezone.now() + timedelta(days=30),
    is_active=True
)

# Create user
user = CustomUser.objects.create_user(
    email='test@example.com',
    password='Test@123456',
    first_name='Test',
    last_name='User',
    organization=org,
    branch=branch,
    role='owner'
)
user.is_active = True
user.save()

org.owned_by = user
org.save()

print("✅ Test account created!")
print(f"📧 Email: test@example.com")
print(f"🔐 Password: Test@123456")
