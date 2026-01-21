from django.forms import ModelForm, ValidationError
from django import forms
from django.contrib.auth.forms import UserCreationForm
from account.models import CustomUser
from . models import *
from account.models import Branch



class StaffCreateForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'phone_number', 'email', 'role')

        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if CustomUser.objects.filter(email=email).exists():
            raise ValidationError("Email already exists")
        return email


class UserEditForm(ModelForm):
    class Meta:
        model = CustomUser
        fields = ('email', 'branch')

        widgets = {
            'branch' : forms.Select(attrs={'class':'form-select', 'placeholder':'brabch'}),
        }

class UserForm(ModelForm):
    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'phone_number', 'email', 'branch', 'role')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
        }

class ProductForm(ModelForm):
    class Meta:
       model = Product
       fields = ('product_name', 'category', 'brand', 'unit', 'batch_no')

       def __init__(self, *args, **kwargs):
           super(ProductForm, self).__init__(*args, **kwargs)
           self.fields['product_name'].widget.attrs['class'] = 'input'
           self.fields['category'].widget.attrs['class'] = 'select'
           self.fields['brand'].widget.attrs['class'] = 'input'
           self.fields['unit'].widget.attrs['class'] = 'input'
           self.fields['batch_no'].widget.attrs['class'] = 'input'
       
       widgets = {
           'category': forms.Select(attrs={'class':'form-select'})
        }

    def clean(self):
        super(ProductForm, self).clean()

        product_name = self.cleaned_data.get('product_name')
        for product in Product.objects.all():
            if product.product_name == product_name:
                self._errors['product_name'] = self.error_class([
                'The product you tried to create already exists'])

        return self.cleaned_data   
    


class EditProductForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super().__init__(*args, **kwargs)

        if organization:
            # Ensure the product’s current category is always available in queryset
            qs = Category.objects.filter(organization=organization)

            if self.instance and self.instance.category_id:
                qs = qs | Category.objects.filter(id=self.instance.category_id)

            self.fields['category'].queryset = qs.distinct()

        # Show label for empty choice
        self.fields['category'].empty_label = "Select a category"

    class Meta:
        model = Product
        fields = ['product_name', 'brand', 'category', 'unit', 'batch_no']



# class EditProductForm(forms.ModelForm):
#     def __init__(self, *args, **kwargs):
#         organization = kwargs.pop('organization', None)
#         super().__init__(*args, **kwargs)
#         if organization:
#             self.fields['category'].queryset = Category.objects.filter(organization=organization) | Category.objects.filter(id=self.instance.category_id)


#     class Meta:
#         model = Product
#         fields = ['product_name', 'brand', 'category', 'unit', 'batch_no']


# class EditProductForm(ModelForm):
#     class Meta:
#         model = Product
#         fields = ('product_name', 'category', 'brand', 'unit', 'batch_no',)

#         def __init__(self, *args, **kwargs):
#            super(ProductForm, self).__init__(*args, **kwargs)
#            self.fields['product_name'].widget.attrs['class'] = 'input'
#            self.fields['category'].widget.attrs['class'] = 'select'
#            self.fields['brand'].widget.attrs['class'] = 'input'
#            self.fields['unit'].widget.attrs['class'] = 'input'
#            self.fields['batch_no'].widget.attrs['class'] = 'input'

        

class CategoryForm(ModelForm):
    class Meta:
        model = Category
        fields = ('category_name',)

    def clean(self):
        super(CategoryForm, self).clean()

        category_name = self.cleaned_data.get('category_name')

        for category in Category.objects.all():
            if category.category_name == category_name:
                self._errors['category_name'] = self.error_class([
                'The category you tried to create already exists'])

        return self.cleaned_data   

class EditCategoryForm(ModelForm):
    class Meta:
        model = Category
        fields = ('category_name',)

class CreateInventoryForm(ModelForm):
    class Meta:
        model = Inventory
        fields = ('product', 'quantity', 'cost_price', 'sale_price', 'reorder_level')


        widgets = {
                'product': forms.Select(attrs={'class':'form-control form-select'})
            }


    # def clean(self):
    #     super(CreateInventoryForm, self).clean()

    #     product = self.cleaned_data.get('product')

    #     for inventory in Inventory.objects.all():
    #         if inventory.product.product_name == product.product_name:
    #             self._errors['product'] = self.error_class([
    #             'The inventory you tried to create already exists'])

    #     return self.cleaned_data 
    

class AdminCreateInventoryForm(ModelForm):
    class Meta:
        model = Inventory
        fields = ('product', 'branch', 'quantity', 'cost_price', 'sale_price', 'reorder_level')


        widgets = {
                'product': forms.Select(attrs={'class':'form-select'}),
                'branch': forms.Select(attrs={'class':'form-select'})
            }  

class AdminRestockForm(ModelForm):
    class Meta:
        model = Inventory
        fields = ('branch', 'quantity_restocked', 'sale_price', 'cost_price')

        widgets = {
                'branch': forms.Select(attrs={'class':'form-select'})
            }
    

class RestockForm(ModelForm):
    class Meta:
        model = Inventory
        fields = ('quantity_restocked', 'sale_price', 'cost_price')

class ReorderForm(ModelForm):
    class Meta:
        model = Inventory
        fields = ('reorder_level',)


class CreateTicketForm(ModelForm):
    assigned_to = forms.ModelChoiceField(queryset=CustomUser.objects.none(), required=False,
        widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super().__init__(*args, **kwargs)
        if organization:
            self.fields['assigned_to'].queryset = CustomUser.objects.filter(organization=organization)
        # Widgets
        self.fields['title'].widget = forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Issue title'})
        self.fields['description'].widget = forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Describe the issue'})

    class Meta:
        model = ErrorTicket
        fields = ('title', 'description', 'assigned_to')
        exclude = ['staff', 'branch']


class UpdateTicketForm(ModelForm):
    assigned_to = forms.ModelChoiceField(queryset=CustomUser.objects.none(), required=False,
        widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super().__init__(*args, **kwargs)
        if organization:
            self.fields['assigned_to'].queryset = CustomUser.objects.filter(organization=organization)
        self.fields['status'].widget = forms.Select(attrs={'class': 'form-select'})

    class Meta:
        model = ErrorTicket
        fields = ('status', 'assigned_to')


class TicketCommentForm(ModelForm):
    class Meta:
        model = TicketComment
        fields = ('content',)
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Add a comment...'})
        }

class PaymentForm(ModelForm):
    class Meta:
        model = Sale
        fields = ('method',)

class AddCountForm(ModelForm):
    class Meta:
        model = Inventory
        fields = ('count',)
        widgets = {
            'count': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Physical count', 'min': 0})
        }


class UploadCountForm(forms.Form):
    """Form for bulk importing physical counts via CSV/Excel"""
    file = forms.FileField(
        required=True,
        help_text='Upload CSV or Excel file with columns: product_name, count',
        widget=forms.FileInput(attrs={'accept': '.csv,.xlsx,.xls', 'class': 'form-control'})
    )


class UploadProductForm(forms.Form):
    upload_file = forms.FileField(
        required=False,
        help_text='Upload CSV or Excel file with columns: product_name, category, brand, unit, batch_no, cost_price, sale_price, quantity, reorder_level',
        widget=forms.FileInput(attrs={'accept': '.csv,.xlsx,.xls'})
    )
    product_name = forms.CharField(max_length=150, required=False)
    category = forms.ModelChoiceField(queryset=Category.objects.none(), required=False)
    brand = forms.CharField(max_length=150, required=False)
    unit = forms.CharField(max_length=50, required=False)
    batch_no = forms.CharField(max_length=20, required=False)
    cost_price = forms.FloatField(required=False)
    sale_price = forms.FloatField(required=False)
    quantity = forms.IntegerField(min_value=0, required=False)
    reorder_level = forms.IntegerField(min_value=0, required=False)

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super().__init__(*args, **kwargs)
        if organization:
            self.fields['category'].queryset = Category.objects.filter(organization=organization)
        for field in self.fields.values():
            css = 'form-control'
            if isinstance(field.widget, forms.Select):
                css = 'form-select'
            field.widget.attrs.setdefault('class', css)

    def clean(self):
        cleaned_data = super().clean()
        upload_file = cleaned_data.get('upload_file')
        product_name = cleaned_data.get('product_name')
        
        # Either file upload or manual entry required, not both
        if not upload_file and not product_name:
            raise forms.ValidationError('Please either upload a file or enter product name for manual entry.')
        
        # If manual entry (product_name provided but no file), validate required fields
        if product_name and not upload_file:
            required_fields = {'category': 'Category', 'cost_price': 'Cost Price', 'sale_price': 'Sale Price', 'quantity': 'Quantity'}
            for field_name, field_label in required_fields.items():
                if not cleaned_data.get(field_name):
                    raise forms.ValidationError(f'{field_label} is required when using manual entry.')
        
        return cleaned_data


