from django.contrib import admin

# Register your models here.

from .models import MarketData, USTreasuryYields, Option, ProductName, DeliveryMonth

admin.site.register(MarketData)
admin.site.register(USTreasuryYields)
admin.site.register(Option)
admin.site.register(ProductName)
admin.site.register(DeliveryMonth)