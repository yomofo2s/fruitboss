from django.conf import settings

from .cart import Cart, wishlist_ids


def shop(request):
    return {
        "SHOP": settings.SHOP,
        "cart_count": Cart(request).count(),
        "wishlist_ids": wishlist_ids(request),
    }
