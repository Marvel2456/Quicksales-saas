from django.forms import ModelForm
from django import forms
from .models import Branch


class CreateBranchForm(ModelForm):
    class Meta:
        model = Branch
        fields = ['name', 'address']

class EditBranchForm(ModelForm):
    class Meta:
        model = Branch
        fields = ['name', 'address']
