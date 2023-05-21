from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import MarketData, ProductName, DeliveryMonth

# This signal is triggered whenever a new MarketData instance is saved

@receiver(post_save, sender=MarketData)
def create_product_name_and_delivery_month(sender, instance, created, **kwargs):
    if created:
        # Create new ProductName and DeliveryMonth instances if they do not exist
        ProductName.objects.get_or_create(name=instance.product_name)
        DeliveryMonth.objects.get_or_create(month=instance.delivery_month)