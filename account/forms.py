from django.forms import ModelForm
from django import forms
from django.contrib.auth.forms import SetPasswordForm
from .models import Branch, CustomUser, ActivityLog, Organization
from django.contrib.auth.forms import UserCreationForm, UserChangeForm




class OwnerRegisterForm(UserCreationForm):
    organization_name = forms.CharField(max_length=255, required=True, label='Organization Name')
    organization_country = forms.CharField(max_length=300, required=False, label='Organization Country')
    organization_logo = forms.ImageField(required=False, label='Organization Logo')
    brand_color = forms.CharField(
        max_length=7, 
        required=False, 
        initial='#007bff',
        label='Brand Color',
        help_text='Hex color code (e.g., #007bff)',
        widget=forms.TextInput(attrs={'type': 'color'})
    )
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
            'organization_name', 'organization_country', 'organization_logo', 'brand_color',
            'branch_name', 'branch_address', 'business_type', 'password1', 'password2'
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


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        label='Email',
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Enter your business email',
                'autocomplete': 'email',
            }
        ),
    )


class PasswordResetConfirmForm(SetPasswordForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields['new_password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'New password',
        })
        self.fields['new_password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirm new password',
        })
