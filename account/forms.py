from django.forms import ModelForm
from django import forms
from .models import Branch, CustomUser, ActivityLog, Organization
from django.contrib.auth.forms import UserCreationForm, UserChangeForm




class OwnerRegisterForm(UserCreationForm):
    organization_name = forms.CharField(max_length=255, required=True, label='Organization Name')
    organization_country = forms.CharField(max_length=300, required=False, label='Organization Country')
    branch_name = forms.CharField(max_length=255, required=True, label='Branch Name')
    branch_address = forms.CharField(max_length=255, required=True, label='Branch Address')
    business_type = forms.ChoiceField(
        choices=Organization.BUSINESS_CHOICES,
        required=True,
        label='Business Type'
    )
    class Meta:
        model = CustomUser
        fields = (
            'email', 'first_name', 'last_name', 'phone_number',
            'organization_name', 'branch_name', 'branch_address',
            'business_type', 'password1', 'password2'
        )

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ('email', 'first_name', 'last_name', 'phone_number', 'organization', 'branch', 'role')


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = ('email', 'first_name', 'last_name', 'phone_number', 'organization', 'branch', 'role')

class OrganizationForm(ModelForm):
    class Meta:
        model = Organization
        fields = ['name']

class CreateBranchForm(ModelForm):
    class Meta:
        model = Branch
        fields = ['name', 'address']

class EditBranchForm(ModelForm):
    class Meta:
        model = Branch
        fields = ['name', 'address']
