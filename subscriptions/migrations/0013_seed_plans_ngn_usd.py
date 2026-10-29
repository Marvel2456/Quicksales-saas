from django.db import migrations
from decimal import Decimal


def seed_plans(apps, schema_editor):
    Plan = apps.get_model('subscriptions', 'Plan')

    # 1. Free Trial Plan
    Plan.objects.update_or_create(
        tier='free',
        size='starter',
        billing_frequency='monthly',
        defaults={
            'name': 'Free Trial',
            'price': Decimal('0.00'),
            'price_usd': Decimal('0.00'),
            'duration_in_days': 14,
            'description': '14-day free trial plan',
            'max_users': 1,
            'max_branches': 1,
            'max_products': 50,
            'disable_store': False,
            'has_online_store': True,
        }
    )

    base_prices_ngn = {
        'basic': {'starter': Decimal('15000.00'), 'large': Decimal('25000.00'), 'xl': Decimal('40000.00')},
        'growth': {'starter': Decimal('35000.00'), 'large': Decimal('60000.00'), 'xl': Decimal('100000.00')},
        'premium': {'starter': Decimal('80000.00'), 'large': Decimal('150000.00'), 'xl': Decimal('250000.00')},
        'invoice': {'starter': Decimal('30000.00'), 'large': Decimal('50000.00'), 'xl': Decimal('85000.00')},
    }

    base_prices_usd = {
        'basic': {'starter': Decimal('15.00'), 'large': Decimal('25.00'), 'xl': Decimal('40.00')},
        'growth': {'starter': Decimal('35.00'), 'large': Decimal('60.00'), 'xl': Decimal('100.00')},
        'premium': {'starter': Decimal('80.00'), 'large': Decimal('150.00'), 'xl': Decimal('250.00')},
        'invoice': {'starter': Decimal('30.00'), 'large': Decimal('50.00'), 'xl': Decimal('85.00')},
    }

    frequencies = {
        'monthly': {'multiplier': Decimal('1.00'), 'duration': 30},
        'quarterly': {'multiplier': Decimal('0.95'), 'duration': 90},
        'annually': {'multiplier': Decimal('0.90'), 'duration': 365},
    }

    tier_features = {
        'basic': {'users': 1, 'branches': 1, 'products': 100, 'disable_store': False, 'has_online_store': True},
        'growth': {'users': 5, 'branches': 5, 'products': 1000, 'disable_store': False, 'has_online_store': True},
        'premium': {'users': 20, 'branches': 20, 'products': 5000, 'disable_store': False, 'has_online_store': True},
        'invoice': {'users': 5, 'branches': 5, 'products': 1000, 'disable_store': True, 'has_online_store': False},
    }

    tier_display_names = {
        'basic': 'Basic',
        'growth': 'Growth',
        'premium': 'Premium',
        'invoice': 'Invoice (No Store)',
    }

    size_display_names = {
        'starter': 'Starter',
        'large': 'Large',
        'xl': 'XL',
    }

    freq_display_names = {
        'monthly': 'Monthly',
        'quarterly': 'Quarterly',
        'annually': 'Annually',
    }

    for tier, sizes in base_prices_ngn.items():
        for size, ngn_price in sizes.items():
            usd_price = base_prices_usd[tier][size]
            feat = tier_features[tier]

            for freq, freq_data in frequencies.items():
                multiplier = freq_data['multiplier']
                duration = freq_data['duration']

                final_ngn = (ngn_price * multiplier).quantize(Decimal('0.01'))
                final_usd = (usd_price * multiplier).quantize(Decimal('0.01'))

                name = f"{tier_display_names[tier]} {size_display_names[size]} - {freq_display_names[freq]}"
                desc = f"{tier_display_names[tier]} plan with {size_display_names[size]} capacity ({freq_display_names[freq]})"

                Plan.objects.update_or_create(
                    tier=tier,
                    size=size,
                    billing_frequency=freq,
                    defaults={
                        'name': name,
                        'price': final_ngn,
                        'price_usd': final_usd,
                        'duration_in_days': duration,
                        'description': desc,
                        'max_users': feat['users'],
                        'max_branches': feat['branches'],
                        'max_products': feat['products'],
                        'disable_store': feat['disable_store'],
                        'has_online_store': feat['has_online_store'],
                    }
                )


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0012_plan_has_online_store'),
    ]

    operations = [
        migrations.RunPython(seed_plans, migrations.RunPython.noop),
    ]
