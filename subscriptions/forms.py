from django import forms
from .models import Coupon, CouponRedemption


class CouponForm(forms.ModelForm):
    """Form for creating and editing coupons (admin only)"""
    
    class Meta:
        model = Coupon
        fields = ('code', 'type', 'value', 'duration_days', 'max_uses', 'start_date', 'end_date', 'is_active')
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., SAVE10'}),
            'type': forms.Select(attrs={'class': 'form-control'}),
            'value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'duration_days': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'max_uses': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'start_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'end_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local', 'required': False}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def clean_code(self):
        code = self.cleaned_data['code'].upper()
        if Coupon.objects.filter(code=code).exclude(id=self.instance.id).exists():
            raise forms.ValidationError("A coupon with this code already exists.")
        return code
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and end_date <= start_date:
            raise forms.ValidationError("End date must be after start date.")
        
        coupon_type = cleaned_data.get('type')
        value = cleaned_data.get('value')
        
        if coupon_type == 'percent' and value > 100:
            raise forms.ValidationError("Percent discount cannot exceed 100%.")
        
        if coupon_type in ('percent', 'fixed') and value <= 0:
            raise forms.ValidationError("Discount value must be greater than 0.")
        
        return cleaned_data


class CouponCodeForm(forms.Form):
    """Simple form for applying a coupon code during checkout"""
    coupon_code = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter coupon code (optional)',
            'autocomplete': 'off',
        })
    )
    
    def clean_coupon_code(self):
        coupon_code = self.cleaned_data['coupon_code'].strip().upper()
        return coupon_code
