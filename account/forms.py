from django.forms import ModelForm
from django import forms
from .models import Branch, Pos


class CreateBranchForm(ModelForm):
    class Meta:
        model = Branch
        fields = ['branch_name', 'branch_address', 'shop']

        widgets = {
            'shop' : forms.Select(attrs={'class':'form-select form-control'})
        }

class EditBranchForm(ModelForm):
    class Meta:
        model = Branch
        fields = ['branch_name', 'branch_address']

        
class CreatePosForm(ModelForm):
    class Meta:
        model = Pos
        fields = ('pos_name', 'branch',)

        widgets = {
            'branch' : forms.Select(attrs={'class':'form-select'})
        }

class EditPosForm(ModelForm):
    class Meta:
        model = Pos
        fields = ('pos_name', 'branch')