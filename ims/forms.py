from django.forms import ModelForm, ValidationError
from django import forms
from django.contrib.auth.forms import UserCreationForm
from account.models import CustomUser
from . models import *
from account.models import Branch

class UserCreateForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = (
            'username', 'password1', 'password2', 'is_admin', 'is_sub_admin', 'is_work_staff', 'branch', 'pos'
            )

        widgets = {
            'branch' : forms.Select(attrs={'class':'form-select form-control', 'placeholder':'brabch'}),
            'pos': forms.Select(attrs={'class':'form-control', 'placeholder':'Pos'})
        }


class UserEditForm(ModelForm):
    class Meta:
        model = CustomUser
        fields = ('username', 'is_admin', 'is_sub_admin', 'is_work_staff', 'branch', 'pos')

        widgets = {
            'branch' : forms.Select(attrs={'class':'form-select', 'placeholder':'brabch'}),
            'pos': forms.Select(attrs={'class':'form-select', 'placeholder':'Pos'})
        }

class UserForm(ModelForm):
    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'phone_number', 'address')

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

class EditProductForm(ModelForm):
    class Meta:
        model = Product
        fields = ('product_name', 'category', 'brand', 'unit', 'batch_no',)

        def __init__(self, *args, **kwargs):
           super(ProductForm, self).__init__(*args, **kwargs)
           self.fields['product_name'].widget.attrs['class'] = 'input'
           self.fields['category'].widget.attrs['class'] = 'select'
           self.fields['brand'].widget.attrs['class'] = 'input'
           self.fields['unit'].widget.attrs['class'] = 'input'
           self.fields['batch_no'].widget.attrs['class'] = 'input'

        # widget = {
        #     'product_name' : forms.TextInput(attrs={'class':'form-control', 'placeholder':'Product'}),
        #     'category' : forms.Select(attrs={'class':'form-select form-control', 'placeholder':'Category'}),
        #     'brand': forms.TextInput(attrs={'class':'form-control', 'placeholder':'Brand'}),
        #     'unit': forms.TextInput(attrs={'class':'form-control', 'placeholder':'Unit'}),
        #     'batch_no': forms.TextInput(attrs={'class':'form-control', 'placeholder':'Batch No'})
        # }

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
    class Meta:
        model = ErrorTicket
        fields = ('title', 'description')
        exclude = ['staff', 'pos', 'branch']

class UpdateTicketForm(ModelForm):
    class Meta:
        model = ErrorTicket
        fields = ('status',)

        widgets = {
            'status': forms.Select(attrs={'class':'form-select', 'placeholder':'status', 'required':True})
        }

class PaymentForm(ModelForm):
    class Meta:
        model = Sale
        fields = ('method',)

class AddCountForm(ModelForm):
    class Meta:
        model = Inventory
        fields = ('count',)


