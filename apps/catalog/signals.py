from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Product


class SkuChangeError(Exception):
    """Raised when code tries to change a product's SKU after creation."""


@receiver(pre_save, sender=Product)
def forbid_sku_change(sender, instance: Product, **kwargs) -> None:
    # Invariant, not a business rule: a SKU is printed on packing slips and orders.
    loaded = getattr(instance, "_loaded_sku", None)
    if instance.pk and loaded and instance.sku != loaded:
        raise SkuChangeError(f"SKU {loaded} cannot change (attempted {instance.sku}).")


@receiver(post_save, sender=Product)
def remember_saved_sku(sender, instance: Product, **kwargs) -> None:
    instance._loaded_sku = instance.sku
