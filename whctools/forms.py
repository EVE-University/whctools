from django import forms
from .models import Acl

class AclsForm(forms.ModelForm):
    class Meta:
        model = Acl
        fields = ['name', 'description']