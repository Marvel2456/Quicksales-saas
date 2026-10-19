from django.forms import ModelForm
from django import forms
from django.contrib.auth.forms import SetPasswordForm
from .models import Branch, CustomUser, ActivityLog, Organization
from django.contrib.auth.forms import UserCreationForm, UserChangeForm




COUNTRY_CHOICES = [
    ('Nigeria', 'Nigeria (NGN)'),
    ('Ghana', 'Ghana'),
    ('Kenya', 'Kenya'),
    ('South Africa', 'South Africa'),
    ('Rwanda', 'Rwanda'),
    ('Benin', 'Benin'),
    ('Cameroon', 'Cameroon'),
    ("Côte d'Ivoire", "Côte d'Ivoire"),
    ('Gambia', 'Gambia'),
    ('Guinea', 'Guinea'),
    ('Liberia', 'Liberia'),
    ('Senegal', 'Senegal'),
    ('Sierra Leone', 'Sierra Leone'),
    ('Togo', 'Togo'),
    ('Egypt', 'Egypt'),
    ('United Kingdom', 'United Kingdom'),
    ('United States', 'United States'),
    ('Canada', 'Canada'),
    ('Others', 'Others'),
]


class OwnerRegisterForm(forms.Form):
    """
    Custom form for owner registration that doesn't inherit from UserCreationForm
    to avoid email uniqueness validation issues in multi-org setup.
    """
    email = forms.EmailField(
        required=True, 
        label='Business Email',
        error_messages={'required': 'Business email is required.'}
    )
    first_name = forms.CharField(
        max_length=100, 
        required=True, 
        label='First Name',
        error_messages={'required': 'First name is required.'}
    )
    last_name = forms.CharField(
        max_length=100, 
        required=True, 
        label='Last Name',
        error_messages={'required': 'Last name is required.'}
    )
    phone_number = forms.CharField(
        max_length=100, 
        required=True, 
        label='Phone Number',
        error_messages={'required': 'Phone number is required.'}
    )
    password1 = forms.CharField(widget=forms.PasswordInput, label='Password', required=False)
    password2 = forms.CharField(widget=forms.PasswordInput, label='Confirm Password', required=False)
    
    organization_name = forms.CharField(
        max_length=255, 
        required=True, 
        label='Organization Name',
        error_messages={'required': 'Organization name cannot be empty. Please enter your organization name.'}
    )
    organization_country = forms.ChoiceField(
        choices=[('', 'Select Country')] + COUNTRY_CHOICES,
        required=True,
        label='Business Country',
        error_messages={
            'required': 'Please select your country.',
            'invalid_choice': 'Please select a valid country.',
        }
    )
    organization_logo = forms.ImageField(required=False, label='Organization Logo')
    brand_color = forms.CharField(
        max_length=7, 
        required=False, 
        initial='#007bff',
        label='Brand Color',
        help_text='Hex color code (e.g., #007bff)',
        widget=forms.TextInput(attrs={'type': 'color'})
    )
    branch_name = forms.CharField(
        max_length=255, 
        required=True, 
        label='Branch Name',
        error_messages={
            'required': 'Branch name cannot be empty. Please enter a branch name.',
        }
    )
    branch_address = forms.CharField(
        max_length=255, 
        required=True, 
        label='Branch Address',
        error_messages={
            'required': 'Branch address cannot be empty. Please enter the branch address.',
        }
    )
    business_type = forms.ChoiceField(
        choices=Organization.BUSINESS_CHOICES,
        required=True,
        label='Business Type',
        error_messages={'required': 'Please select your business type.'}
    )

    def clean_first_name(self):
        val = self.cleaned_data.get('first_name', '').strip()
        if not val:
            raise forms.ValidationError("First name is required.")
        return val

    def clean_last_name(self):
        val = self.cleaned_data.get('last_name', '').strip()
        if not val:
            raise forms.ValidationError("Last name is required.")
        return val

    def clean_phone_number(self):
        val = self.cleaned_data.get('phone_number', '').strip()
        if not val:
            raise forms.ValidationError("Phone number is required.")
        return val

    def clean_organization_name(self):
        val = self.cleaned_data.get('organization_name', '').strip()
        if not val:
            raise forms.ValidationError("Organization name cannot be empty. Please enter your organization name.")
        return val

    def clean_branch_name(self):
        branch_name = self.cleaned_data.get('branch_name', '').strip()
        if not branch_name:
            raise forms.ValidationError("Branch name cannot be empty. Please enter a branch name.")
        return branch_name

    def clean_branch_address(self):
        branch_address = self.cleaned_data.get('branch_address', '').strip()
        if not branch_address:
            raise forms.ValidationError("Branch address cannot be empty. Please enter the branch address.")
        return branch_address

    def clean_organization_country(self):
        country = self.cleaned_data.get('organization_country', '').strip()
        if not country:
            raise forms.ValidationError("Please select your country.")
        return country
    
    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        # Check if user already exists
        user_exists = False
        if email:
            try:
                CustomUser.objects.get(email__iexact=email)
                user_exists = True
            except CustomUser.DoesNotExist:
                pass

        # If user doesn't exist, passwords are required
        if not user_exists:
            if not password1:
                self.add_error('password1', "Password is required for new users.")
            elif len(password1) < 8:
                self.add_error('password1', "Password must be at least 8 characters long.")
                
            if not password2:
                self.add_error('password2', "Please confirm your password.")
            elif password1 and password2 and password1 != password2:
                self.add_error('password2', "Passwords don't match.")
        
        return cleaned_data

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
