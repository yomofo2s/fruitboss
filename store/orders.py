"""Order lifecycle: placing, paying (Paystack), cancelling and restocking."""
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from . import paystack
from .cart import Cart
from .models import Order, OrderItem, Payment, Product

log = logging.getLogger(__name__)


class StockError(Exception):
    pass


def create_order(cart, form):
    """Create the order and reserve stock atomically. Raises StockError if stock changed under us."""
    with transaction.atomic():
        products = Product.objects.select_for_update().filter(pk__in=cart.data.keys(), is_active=True)
        by_id = {p.pk: p for p in products}
        wanted = []
        for key, qty in cart.data.items():
            p = by_id.get(int(key))
            if p is None or p.stock < qty:
                raise StockError(f"Sorry, {p.name if p else 'an item'} is no longer available "
                                 "in the quantity you wanted. Please review your cart.")
            wanted.append((p, qty))
        if not wanted:
            raise StockError("Your cart is empty.")

        subtotal = sum((p.current_price * q for p, q in wanted))
        fee = Cart.delivery_fee(subtotal)
        order = form.save(commit=False)
        order.subtotal, order.delivery_fee, order.total = subtotal, fee, subtotal + fee
        order.save()
        for p, qty in wanted:
            OrderItem.objects.create(order=order, product=p, name=p.name, unit=p.unit,
                                     unit_price=p.current_price, quantity=qty)
            p.stock -= qty
            p.save(update_fields=["stock"])
        # Card orders are announced only once they are paid.
        if order.payment_method != Order.Payment.CARD:
            transaction.on_commit(lambda: send_order_emails(order))
    return order


def send_order_emails(order, note=""):
    lines = "\n".join(f"  {i.quantity} x {i.name} @ {i.unit_price}" for i in order.items.all())
    body = (f"Order {order.reference}\n\n{lines}\n\nSubtotal: {order.subtotal}\n"
            f"Delivery: {order.delivery_fee}\nTotal: {order.total}\n"
            f"Payment: {order.get_payment_method_display()} ({'paid' if order.paid else 'not paid yet'})\n")
    send_mail(f"Your Fruitboss order {order.reference}",
              f"Hi {order.full_name},\n\nThanks for your order! We'll be in touch shortly.\n\n{body}",
              None, [order.email], fail_silently=True)
    send_mail(f"New order {order.reference}",
              f"{note}{body}\nCustomer: {order.full_name}, {order.phone}, {order.email}\n"
              f"Deliver to: {order.address}, {order.city}, {order.state}\nNotes: {order.notes}",
              None, [settings.SHOP["ORDER_NOTIFY_EMAIL"]], fail_silently=True)


def _alert_shop(subject, body):
    send_mail(subject, body, None, [settings.SHOP["ORDER_NOTIFY_EMAIL"]], fail_silently=True)


# --- Paystack -------------------------------------------------------------------------------------

def start_payment(order, callback_url):
    """Create a Paystack transaction for the order and return the URL to send the customer to."""
    reference = f"{order.reference}-{secrets.token_hex(3)}"
    data = paystack.initialize(
        email=order.email, amount_kobo=paystack.to_kobo(order.total), reference=reference,
        callback_url=callback_url, metadata={"order": order.reference},
    )
    Payment.objects.create(order=order, reference=reference)
    return data["authorization_url"]


def mark_paid(reference, amount_kobo, currency):
    """Record a successful Paystack charge. Safe to call repeatedly (callback and webhook both do).

    Returns the order, or None if the reference is unknown or the amount/currency doesn't match.
    """
    with transaction.atomic():
        try:
            payment = Payment.objects.select_for_update().get(reference=reference)
        except Payment.DoesNotExist:
            log.warning("Paystack reference %s matches no payment", reference)
            return None
        order = Order.objects.select_for_update().get(pk=payment.order_id)
        if payment.status == Payment.Status.SUCCESS:
            return order
        if currency != "NGN" or amount_kobo != paystack.to_kobo(order.total):
            log.error("Paystack amount mismatch for %s: got %s %s, expected %s", reference,
                      amount_kobo, currency, paystack.to_kobo(order.total))
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status"])
            return None

        payment.status = Payment.Status.SUCCESS
        payment.save(update_fields=["status"])

        if order.paid:  # customer paid twice (e.g. retried while the first was still processing)
            transaction.on_commit(lambda: _alert_shop(
                f"Duplicate payment for order {order.reference}",
                f"Paystack reference {reference} succeeded but the order was already paid. Please refund."))
            return order

        note = ""
        if order.status == Order.Status.CANCELLED:  # paid after the unpaid-order timeout released the stock
            _reserve_again(order)
            order.status = Order.Status.PENDING
            note = ("NOTE: this order had been cancelled for non-payment before the payment arrived. "
                    "Stock was re-reserved where possible - please check it.\n\n")
        order.paid = True
        if order.status == Order.Status.PENDING:
            order.status = Order.Status.CONFIRMED
        order.save(update_fields=["paid", "status"])
        transaction.on_commit(lambda: send_order_emails(order, note))
    return order


def mark_failed(reference):
    Payment.objects.filter(reference=reference, status=Payment.Status.INITIATED).update(
        status=Payment.Status.FAILED)


# --- Cancelling / stock ----------------------------------------------------------------------------

def _reserve_again(order):
    """Take stock back out for a revived order, never going below zero."""
    for item in order.items.select_related("product"):
        if item.product:
            Product.objects.filter(pk=item.product_id).update(
                stock=F("stock") - min(item.quantity, item.product.stock))


def cancel_unpaid(order):
    """Cancel an unpaid order and put its stock back. Returns True if anything changed."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.paid or order.status != Order.Status.PENDING:
            return False
        for item in order.items.all():
            if item.product_id:
                Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)
        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status"])
    return True


def expire_unpaid_card_orders(minutes=None):
    minutes = settings.SHOP["UNPAID_ORDER_MINUTES"] if minutes is None else minutes
    cutoff = timezone.now() - timedelta(minutes=minutes)
    stale = Order.objects.filter(payment_method=Order.Payment.CARD, paid=False,
                                 status=Order.Status.PENDING, created__lt=cutoff)
    return sum(cancel_unpaid(o) for o in stale)
