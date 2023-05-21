from django import forms
from .models import Option, MarketData, ProductName, DeliveryMonth

"""
This a form for the Option model, users will complete the form on the index.html accordingly.
Note the ProductName and DeliveryMonth models are imported to ensure unique values in the drop down

"""

class OptionForm(forms.ModelForm):
    underlying_future = forms.ModelChoiceField(queryset=ProductName.objects.all())
    delivery_month = forms.ModelChoiceField(queryset=DeliveryMonth.objects.all())

    class Meta:
        model = Option
        fields = ['option_type', 'underlying_future', 'delivery_month', 'strike_price']

class DateRangeForm(forms.Form):
    startDate = forms.DateField(input_formats=['%Y-%m-%d'])
    endDate = forms.DateField(input_formats=['%Y-%m-%d'])