from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from account.models import Branch, CustomUser, Organization, OrganizationMembership


class ResendVerificationTests(TestCase):
	def setUp(self):
		self.user = CustomUser.objects.create_user(
			email='inactive@example.com',
			password='testpass123',
			is_active=False,
		)
		self.organization = Organization.objects.create(
			name='Resend Org',
			owned_by=self.user,
		)
		self.branch = Branch.objects.create(
			organization=self.organization,
			name='Main Branch',
		)
		OrganizationMembership.objects.create(
			user=self.user,
			organization=self.organization,
			branch=self.branch,
			role='owner',
			is_active=True,
		)

	@patch('account.views.task_send_verification_email.delay')
	def test_resend_verification_email_queues_task_for_inactive_user(self, mock_delay):
		response = self.client.post(reverse('resend_verification_email'), {
			'email': self.user.email,
		})

		self.assertRedirects(response, reverse('login'))
		mock_delay.assert_called_once_with(self.user.id, self.organization.id)

	def test_login_shows_resend_option_for_inactive_user(self):
		response = self.client.post(reverse('login'), {
			'email': self.user.email,
		})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Resend verification email')

	@patch('account.views.task_send_verification_email.delay')
	@patch('account.views.deactivate_subscription.apply_async')
	def test_first_time_registration_shows_verification_sent_screen(self, mock_deactivate, mock_delay):
		response = self.client.post(reverse('register'), {
			'email': 'newuser@example.com',
			'first_name': 'New',
			'last_name': 'User',
			'phone_number': '08000000000',
			'password1': 'strongpass123',
			'password2': 'strongpass123',
			'organization_name': 'New Org',
			'organization_country': 'Nigeria',
			'brand_color': '#007bff',
			'branch_name': 'HQ',
			'branch_address': 'Lagos',
			'business_type': 'electronics',
		})

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'account/verification_email_sent.html')
		self.assertContains(response, 'Verification email sent')
		self.assertContains(response, 'Resend verification email')
		mock_delay.assert_called_once()
