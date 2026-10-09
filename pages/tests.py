from django.test import TestCase
from django.urls import reverse
from subscriptions.models import Plan


class LandingPageTests(TestCase):
    def setUp(self):
        Plan.objects.get_or_create(
            tier='basic',
            size='starter',
            billing_frequency='monthly',
            defaults={
                'price': 10000,
                'max_users': 3,
                'max_branches': 1,
                'max_products': 500,
                'has_online_store': True
            }
        )

    def test_landing_page_renders_online_store_section(self):
        response = self.client.get(reverse('landing_page'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('id="online-store"', content)
        self.assertIn('ONLINE STORE & DIGITAL COMMERCE', content)
        self.assertIn('Launch Your 24/7 Digital Storefront', content)
        self.assertIn('Integrated Payments', content)
        self.assertIn('Real-Time Inventory Synchronization', content)
        self.assertIn('Instant Branded Storefront Link', content)
        self.assertIn('How does the Online Storefront feature work?', content)
        self.assertIn('Start free trial', content)


