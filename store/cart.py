"""Session-backed cart and wishlist."""
from decimal import Decimal

from django.conf import settings

from .models import Product

CART_KEY = "cart"
WISHLIST_KEY = "wishlist"


def max_qty(product):
    return min(product.stock, settings.SHOP["MAX_LINE_QUANTITY"])


class Cart:
    def __init__(self, request):
        self.session = request.session
        self.data = self.session.get(CART_KEY, {})

    def _save(self):
        self.session[CART_KEY] = self.data
        self.session.modified = True

    def add(self, product, quantity=1, override=False):
        """Set or increase a line, clamped to available stock. Returns the stored quantity."""
        key = str(product.pk)
        current = 0 if override else self.data.get(key, 0)
        qty = max(0, min(current + quantity, max_qty(product)))
        if qty:
            self.data[key] = qty
        else:
            self.data.pop(key, None)
        self._save()
        return qty

    def remove(self, product_id):
        self.data.pop(str(product_id), None)
        self._save()

    def clear(self):
        self.data = {}
        self._save()

    def lines(self):
        """Cart lines for active products; drops anything that vanished or sold out."""
        products = Product.objects.filter(pk__in=self.data.keys(), is_active=True)
        lines = []
        for p in products:
            qty = min(self.data[str(p.pk)], max_qty(p))
            if qty > 0:
                lines.append({"product": p, "quantity": qty, "total": p.current_price * qty})
        lines.sort(key=lambda l: l["product"].name)
        return lines

    def count(self):
        return sum(self.data.values())

    def subtotal(self, lines=None):
        return sum((l["total"] for l in (lines if lines is not None else self.lines())), Decimal("0"))

    @staticmethod
    def delivery_fee(subtotal):
        shop = settings.SHOP
        if subtotal <= 0 or subtotal >= shop["FREE_DELIVERY_THRESHOLD"]:
            return Decimal("0")
        return shop["DELIVERY_FEE"]

    def summary(self):
        lines = self.lines()
        subtotal = self.subtotal(lines)
        fee = self.delivery_fee(subtotal)
        return {"lines": lines, "subtotal": subtotal, "delivery_fee": fee, "total": subtotal + fee}


def wishlist_ids(request):
    return [int(i) for i in request.session.get(WISHLIST_KEY, [])]


def toggle_wishlist(request, product_id):
    ids = wishlist_ids(request)
    if product_id in ids:
        ids.remove(product_id)
        added = False
    else:
        ids.append(product_id)
        added = True
    request.session[WISHLIST_KEY] = ids
    return added
