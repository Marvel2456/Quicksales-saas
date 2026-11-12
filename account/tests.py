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

	def test_registration_fails_when_branch_name_is_empty(self):
		response = self.client.post(reverse('register'), {
			'email': 'branch_test@example.com',
			'first_name': 'Test',
			'last_name': 'Branch',
			'phone_number': '08000000001',
			'password1': 'strongpass123',
			'password2': 'strongpass123',
			'organization_name': 'No Branch Org',
			'organization_country': 'Nigeria',
			'brand_color': '#007bff',
			'branch_name': '   ',  # whitespace should be invalid
			'branch_address': 'Lagos',
			'business_type': 'electronics',
		})

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'account/register.html')
		self.assertFalse(Organization.objects.filter(name='No Branch Org').exists())
		form = response.context['form']
		self.assertIn('branch_name', form.errors)

	def test_registration_fails_when_country_is_empty(self):
		response = self.client.post(reverse('register'), {
			'email': 'country_test@example.com',
			'first_name': 'Test',
			'last_name': 'Country',
			'phone_number': '08000000002',
			'password1': 'strongpass123',
			'password2': 'strongpass123',
			'organization_name': 'No Country Org',
			'organization_country': '',
			'brand_color': '#007bff',
			'branch_name': 'Main Branch',
			'branch_address': 'Lagos',
			'business_type': 'electronics',
		})

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'account/register.html')
		self.assertFalse(Organization.objects.filter(name='No Country Org').exists())
		form = response.context['form']
		self.assertIn('organization_country', form.errors)

	def test_registration_fails_when_organization_name_is_empty(self):
		response = self.client.post(reverse('register'), {
			'email': 'org_name_test@example.com',
			'first_name': 'Test',
			'last_name': 'Org',
			'phone_number': '08000000003',
			'password1': 'strongpass123',
			'password2': 'strongpass123',
			'organization_name': '   ',  # whitespace should be invalid
			'organization_country': 'Nigeria',
			'brand_color': '#007bff',
			'branch_name': 'Main Branch',
			'branch_address': 'Lagos',
			'business_type': 'electronics',
		})

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'account/register.html')
		form = response.context['form']
		self.assertIn('organization_name', form.errors)

	def test_registration_fails_when_branch_address_is_empty(self):
		response = self.client.post(reverse('register'), {
			'email': 'address_test@example.com',
			'first_name': 'Test',
			'last_name': 'Address',
			'phone_number': '08000000004',
			'password1': 'strongpass123',
			'password2': 'strongpass123',
			'organization_name': 'Valid Org',
			'organization_country': 'Nigeria',
			'brand_color': '#007bff',
			'branch_name': 'Main Branch',
			'branch_address': '   ',  # whitespace should be invalid
			'business_type': 'electronics',
		})

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'account/register.html')
		self.assertFalse(Organization.objects.filter(name='Valid Org').exists())
		form = response.context['form']
		self.assertIn('branch_address', form.errors)


class EmailCaseInsensitivityAndNormalizationTests(TestCase):
	def setUp(self):
		from django.contrib.auth import authenticate
		self.authenticate = authenticate
		# Manually create a user with an uppercase email directly bypassing save()
		# to simulate existing legacy database records on live server
		self.legacy_user = CustomUser(
			first_name="Legacy",
			last_name="Client",
			role="owner",
			is_active=True,
		)
		self.legacy_user.email = "Client@Example.com"
		self.legacy_user.set_password("SecretPassword123!")
		# Call super(CustomUser, self.legacy_user).save() to bypass CustomUser.save() lowercasing
		super(CustomUser, self.legacy_user).save()

		self.org = Organization.objects.create(
			name="Legacy Org",
			slug="legacy-org",
			owned_by=self.legacy_user,
			is_active=True
		)
		self.branch = Branch.objects.create(
			organization=self.org,
			name="Main Branch"
		)
		OrganizationMembership.objects.create(
			user=self.legacy_user,
			organization=self.org,
			branch=self.branch,
			role="owner",
			is_active=True
		)

	def test_authenticate_with_lowercase_when_db_has_uppercase(self):
		# User stored as Client@Example.com in DB
		# Authenticate with all lowercase
		user = self.authenticate(email="client@example.com", password="SecretPassword123!")
		self.assertIsNotNone(user)
		self.assertEqual(user.id, self.legacy_user.id)
		# User record in DB is auto-healed to lowercase
		self.legacy_user.refresh_from_db()
		self.assertEqual(self.legacy_user.email, "client@example.com")

	def test_authenticate_with_all_caps_when_db_has_lowercase(self):
		user = self.authenticate(email="CLIENT@EXAMPLE.COM", password="SecretPassword123!")
		self.assertIsNotNone(user)
		self.assertEqual(user.id, self.legacy_user.id)

	def test_password_remains_strictly_case_sensitive(self):
		# Wrong password casing must fail (return None)
		user = self.authenticate(email="client@example.com", password="secretpassword123!")
		self.assertIsNone(user)

		user2 = self.authenticate(email="Client@Example.com", password="SECRETPASSWORD123!")
		self.assertIsNone(user2)

		# Exact password casing succeeds
		user3 = self.authenticate(email="client@example.com", password="SecretPassword123!")
		self.assertIsNotNone(user3)

	def test_multi_step_login_flow_with_mixed_case_email(self):
		# Step 1: Submit lowercase email
		s1_resp = self.client.post(reverse('login'), {
			'email': 'client@example.com'
		})
		self.assertEqual(s1_resp.status_code, 200)
		self.assertEqual(self.client.session.get('login_email'), 'client@example.com')

		# Step 3: Submit exact case password
		s3_resp = self.client.post(reverse('login'), {
			'password': 'SecretPassword123!'
		})
		self.assertEqual(s3_resp.status_code, 302)
		self.assertNotIn('login', s3_resp.url)

	def test_model_save_and_manager_normalize_email_to_lowercase(self):
		user = CustomUser.objects.create_user(
			email="NewUser@DOMAIN.COM",
			password="Password123!",
		)
		self.assertEqual(user.email, "newuser@domain.com")

		# Direct save with uppercase
		user.email = "ANOTHER@UPPERCASE.COM"
		user.save()
		user.refresh_from_db()
		self.assertEqual(user.email, "another@uppercase.com")

	def test_owner_registration_form_normalizes_email(self):
		from account.forms import OwnerRegisterForm
		form = OwnerRegisterForm(data={
			'email': 'OwnerRegister@Domain.COM',
			'first_name': 'Owner',
			'last_name': 'User',
			'phone_number': '08012345678',
			'password1': 'StrongPass123!',
			'password2': 'StrongPass123!',
			'organization_name': 'New Normalized Org',
			'organization_country': 'Nigeria',
			'branch_name': 'Branch 1',
			'branch_address': 'Address 1',
			'business_type': 'electronics',
		})
		self.assertTrue(form.is_valid(), form.errors)
		self.assertEqual(form.cleaned_data['email'], 'ownerregister@domain.com')

	def test_staff_create_form_normalizes_email(self):
		from ims.forms import StaffCreateForm
		form = StaffCreateForm(
			data={
				'first_name': 'Staff',
				'last_name': 'Member',
				'phone_number': '08098765432',
				'email': 'StaffPerson@DOMAIN.COM',
				'role': 'sales',
			},
			organization=self.org,
			branch=self.branch
		)
		self.assertTrue(form.is_valid(), form.errors)
		self.assertEqual(form.cleaned_data['email'], 'staffperson@domain.com')


