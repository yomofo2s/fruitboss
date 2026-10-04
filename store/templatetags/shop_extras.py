from decimal import Decimal

from django import template
from django.conf import settings

register = template.Library()


@register.filter
def naira(value):
    """12500 -> ₦12,500 ; 12500.5 -> ₦12,500.50"""
    try:
        d = Decimal(value)
    except (TypeError, ValueError, ArithmeticError):
        return value
    fmt = "{:,.0f}" if d == d.to_integral_value() else "{:,.2f}"
    return f"{settings.SHOP['CURRENCY']}{fmt.format(d)}"
