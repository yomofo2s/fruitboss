from decimal import Decimal

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .models import Category, Order, Product

CHECKOUT = {
    "full_name": "Ada Obi", "email": "ada@example.com", "phone": "+234 801 234 5678",
    "address": "1 Test Street", "city": "Ikeja", "state": "Lagos",
    "payment_method": "cod", "accept_terms": "on",
}


class ShopTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fruits = Category.objects.create(name="Fruits")
        cls.apple = Product.objects.create(category=cls.fruits, name="Apple", price=Decimal("3000"), stock=10)
        cls.pear = Product.objects.create(category=cls.fruits, name="Pear", price=Decimal("2000"),
                                          sale_price=Decimal("1000"), stock=2, featured=True)
        cls.hidden = Product.objects.create(category=cls.fruits, name="Hidden", price=1, stock=5, is_active=False)

    def add(self, product, qty=1, **extra):
        return self.client.post(reverse("store:cart_add", args=[product.pk]), {"quantity": qty}, **extra)


class CatalogTests(ShopTestCase):
    def test_pages_render(self):
        for name in ("home", "shop", "cart", "wishlist", "about", "contact"):
            self.assertEqual(self.client.get(reverse(f"store:{name}")).status_code, 200, name)
        self.assertEqual(self.client.get(self.apple.get_absolute_url()).status_code, 200)

    def test_inactive_hidden(self):
        self.assertNotContains(self.client.get(reverse("store:shop")), "Hidden")
        self.assertEqual(self.client.get(self.hidden.get_absolute_url()).status_code, 404)

    def test_search_filter_sort(self):
        r = self.client.get(reverse("store:shop"), {"q": "pear"})
        self.assertContains(r, "Pear")
        self.assertNotContains(r, "Apple")
        r = self.client.get(reverse("store:shop"), {"sort": "price_asc"})
        names = [p.name for p in r.context["page"]]
        self.assertEqual(names, ["Pear", "Apple"])  # ordered by list price asc
        self.assertEqual(self.client.get(reverse("store:shop"), {"category": "nope"}).status_code, 404)

    def test_sale_price(self):
        self.assertEqual(self.pear.current_price, Decimal("1000"))
        self.assertEqual(self.pear.discount_percent, 50)
        self.assertEqual(self.apple.discount_percent, 0)


class CartTests(ShopTestCase):
    def test_add_update_remove(self):
        self.add(self.apple, 2)
        self.add(self.apple, 1)
        r = self.client.get(reverse("store:cart"))
        self.assertEqual(r.context["subtotal"], Decimal("9000"))
        self.client.post(reverse("store:cart_update", args=[self.apple.pk]), {"quantity": 1})
        self.assertEqual(self.client.get(reverse("store:cart")).context["subtotal"], Decimal("3000"))
        self.client.post(reverse("store:cart_remove", args=[self.apple.pk]))
        self.assertEqual(self.client.get(reverse("store:cart")).context["lines"], [])

    def test_quantity_capped_at_stock(self):
        self.add(self.pear, 99)
        self.assertEqual(self.client.get(reverse("store:cart")).context["lines"][0]["quantity"], 2)

    def test_add_get_not_allowed_and_inactive_404(self):
        self.assertEqual(self.client.get(reverse("store:cart_add", args=[self.apple.pk])).status_code, 405)
        self.assertEqual(self.add(self.hidden).status_code, 404)

    def test_ajax_add_returns_count(self):
        r = self.add(self.apple, 3, headers={"x-requested-with": "XMLHttpRequest"})
        self.assertEqual(r.json()["cart_count"], 3)

    def test_delivery_fee_and_free_threshold(self):
        self.add(self.apple, 1)
        self.assertEqual(self.client.get(reverse("store:cart")).context["delivery_fee"], Decimal("1500"))
        self.add(self.apple, 7)  # 24,000 >= threshold
        self.assertEqual(self.client.get(reverse("store:cart")).context["delivery_fee"], Decimal("0"))

    def test_open_redirect_blocked(self):
        r = self.client.post(reverse("store:cart_add", args=[self.apple.pk]), {"next": "https://evil.example/"})
        self.assertEqual(r.url, reverse("store:cart"))

    def test_wishlist_toggle(self):
        url = reverse("store:wishlist_toggle", args=[self.apple.pk])
        self.assertTrue(self.client.post(url, headers={"x-requested-with": "XMLHttpRequest"}).json()["added"])
        self.assertContains(self.client.get(reverse("store:wishlist")), "Apple")
        self.assertFalse(self.client.post(url, headers={"x-requested-with": "XMLHttpRequest"}).json()["added"])


class CheckoutTests(ShopTestCase):
    def test_empty_cart_redirects(self):
        self.assertRedirects(self.client.get(reverse("store:checkout")), reverse("store:shop"))

    def test_place_order(self):
        self.add(self.apple, 2)
        self.add(self.pear, 1)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(reverse("store:checkout"), CHECKOUT)
        order = Order.objects.get()
        self.assertRedirects(r, order.get_absolute_url())
        self.assertEqual(order.subtotal, Decimal("7000"))  # 2*3000 + 1000
        self.assertEqual(order.delivery_fee, Decimal("1500"))
        self.assertEqual(order.total, Decimal("8500"))
        self.assertEqual(order.items.count(), 2)
        self.apple.refresh_from_db(); self.pear.refresh_from_db()
        self.assertEqual((self.apple.stock, self.pear.stock), (8, 1))
        self.assertEqual(len(mail.outbox), 2)
        # cart is emptied
        self.assertEqual(self.client.get(reverse("store:cart")).context["lines"], [])

    def test_validation_errors_keep_cart_and_stock(self):
        self.add(self.apple, 1)
        r = self.client.post(reverse("store:checkout"), {**CHECKOUT, "phone": "abc", "accept_terms": ""})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.apple.refresh_from_db()
        self.assertEqual(self.apple.stock, 10)

    def test_stock_gone_by_checkout(self):
        self.add(self.pear, 2)
        Product.objects.filter(pk=self.pear.pk).update(stock=1)  # someone else bought one
        r = self.client.post(reverse("store:checkout"), CHECKOUT)
        self.assertRedirects(r, reverse("store:cart"))
        self.assertEqual(Order.objects.count(), 0)

    def test_order_page_private_to_session(self):
        self.add(self.apple)
        self.client.post(reverse("store:checkout"), CHECKOUT)
        order = Order.objects.get()
        self.assertEqual(self.client.get(order.get_absolute_url()).status_code, 200)
        self.client.logout()
        from django.test import Client
        self.assertEqual(Client().get(order.get_absolute_url()).status_code, 404)


class ContactTests(ShopTestCase):
    def test_contact_and_subscribe(self):
        r = self.client.post(reverse("store:contact"),
                             {"name": "A", "email": "a@example.com", "subject": "Hi", "message": "Hello"})
        self.assertRedirects(r, reverse("store:contact"))
        self.client.post(reverse("store:subscribe"), {"email": "A@Example.com"})
        self.client.post(reverse("store:subscribe"), {"email": "a@example.com"})
        from .models import ContactMessage, Subscriber
        self.assertEqual((ContactMessage.objects.count(), Subscriber.objects.count()), (1, 1))


# --- Paystack ---------------------------------------------------------------------------------------

import hashlib
import hmac
import json
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from . import orders, paystack
from .models import Payment

SECRET = "sk_test_secret"




@override_settings(PAYSTACK_SECRET_KEY=SECRET, SHOP={**settings.SHOP, "PAYSTACK_ENABLED": True})
class PaystackTests(ShopTestCase):
    def place_card_order(self, qty=1):
        self.add(self.apple, qty)
        with mock.patch("store.paystack.initialize",
                        return_value={"authorization_url": "https://checkout.paystack.com/abc"}) as init:
            r = self.client.post(reverse("store:checkout"), {**CHECKOUT, "payment_method": "card"})
        return r, init

    def charge(self, order, **over):
        payment = order.payments.get()
        data = {"status": "success", "reference": payment.reference,
                "amount": paystack.to_kobo(order.total), "currency": "NGN", **over}
        return payment, data

    def test_card_option_only_when_enabled(self):
        self.add(self.apple)
        self.assertContains(self.client.get(reverse("store:checkout")), "Pay online")
        with override_settings(SHOP={**settings.SHOP, "PAYSTACK_ENABLED": False}):
            self.assertNotContains(self.client.get(reverse("store:checkout")), "Pay online")
            r = self.client.post(reverse("store:checkout"), {**CHECKOUT, "payment_method": "card"})
            self.assertEqual(r.status_code, 200)  # card rejected when Paystack is off

    def test_checkout_redirects_to_paystack_with_kobo_amount(self):
        with self.captureOnCommitCallbacks(execute=True):
            r, init = self.place_card_order(qty=2)
        self.assertRedirects(r, "https://checkout.paystack.com/abc", fetch_redirect_response=False)
        order = Order.objects.get()
        kwargs = init.call_args.kwargs
        self.assertEqual(kwargs["amount_kobo"], 750000)  # 2*3000 + 1500 delivery = 7,500 naira
        self.assertEqual(kwargs["email"], "ada@example.com")
        self.assertTrue(kwargs["callback_url"].endswith(reverse("store:payment_callback")))
        self.assertFalse(order.paid)
        self.assertEqual(order.payments.get().status, "initiated")
        self.assertEqual(len(mail.outbox), 0)  # nothing announced until paid
        self.apple.refresh_from_db()
        self.assertEqual(self.apple.stock, 8)  # reserved

    def test_paystack_down_keeps_order_and_offers_retry(self):
        self.add(self.apple)
        with mock.patch("store.paystack.initialize", side_effect=paystack.PaystackError("boom")):
            r = self.client.post(reverse("store:checkout"), {**CHECKOUT, "payment_method": "card"})
        order = Order.objects.get()
        self.assertRedirects(r, order.get_absolute_url())
        self.assertContains(self.client.get(order.get_absolute_url()), "Pay ")

    def test_callback_success_marks_paid_once(self):
        self.place_card_order()
        order = Order.objects.get()
        payment, data = self.charge(order)
        with mock.patch("store.paystack.verify", return_value=data):
            with self.captureOnCommitCallbacks(execute=True):
                r = self.client.get(reverse("store:payment_callback"), {"reference": payment.reference})
            self.assertRedirects(r, order.get_absolute_url())
            with self.captureOnCommitCallbacks(execute=True):  # second hit (e.g. refresh / webhook) is a no-op
                self.client.get(reverse("store:payment_callback"), {"reference": payment.reference})
        order.refresh_from_db()
        self.assertTrue(order.paid)
        self.assertEqual(order.status, "confirmed")
        self.assertEqual(len(mail.outbox), 2)  # one customer + one shop email, not four

    def test_callback_amount_mismatch_not_paid(self):
        self.place_card_order()
        order = Order.objects.get()
        payment, data = self.charge(order, amount=100)
        with mock.patch("store.paystack.verify", return_value=data):
            self.client.get(reverse("store:payment_callback"), {"reference": payment.reference})
        order.refresh_from_db()
        self.assertFalse(order.paid)

    def test_callback_failed_payment_allows_retry(self):
        self.place_card_order()
        order = Order.objects.get()
        payment, data = self.charge(order, status="failed")
        with mock.patch("store.paystack.verify", return_value=data):
            self.client.get(reverse("store:payment_callback"), {"reference": payment.reference})
        payment.refresh_from_db()
        self.assertEqual(payment.status, "failed")
        with mock.patch("store.paystack.initialize", return_value={"authorization_url": "https://pay/2"}):
            r = self.client.post(reverse("store:order_pay", args=[order.reference]))
        self.assertEqual(r.url, "https://pay/2")
        self.assertEqual(order.payments.count(), 2)
        self.assertEqual(len({p.reference for p in order.payments.all()}), 2)  # fresh reference per attempt

    def test_callback_unknown_reference_404(self):
        self.assertEqual(self.client.get(reverse("store:payment_callback"), {"reference": "nope"}).status_code, 404)

    def test_callback_from_other_browser_hides_order_details(self):
        self.place_card_order()
        order = Order.objects.get()
        payment, data = self.charge(order)
        from django.test import Client
        with mock.patch("store.paystack.verify", return_value=data):
            r = Client().get(reverse("store:payment_callback"), {"reference": payment.reference})
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Ada Obi")

    def webhook(self, payload, secret=SECRET, sign=True):
        body = json.dumps(payload).encode()
        headers = {}
        if sign:
            headers["HTTP_X_PAYSTACK_SIGNATURE"] = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
        return self.client.post(reverse("store:paystack_webhook"), body, content_type="application/json", **headers)

    def test_webhook_marks_paid(self):
        self.place_card_order()
        order = Order.objects.get()
        payment, data = self.charge(order)
        r = self.webhook({"event": "charge.success", "data": data})
        self.assertEqual(r.status_code, 200)
        order.refresh_from_db()
        self.assertTrue(order.paid)

    def test_webhook_rejects_bad_or_missing_signature(self):
        self.place_card_order()
        order = Order.objects.get()
        payment, data = self.charge(order)
        self.assertEqual(self.webhook({"event": "charge.success", "data": data}, secret="wrong").status_code, 401)
        self.assertEqual(self.webhook({"event": "charge.success", "data": data}, sign=False).status_code, 401)
        order.refresh_from_db()
        self.assertFalse(order.paid)

    def test_expire_cancels_unpaid_and_restocks(self):
        self.place_card_order(qty=3)
        order = Order.objects.get()
        Order.objects.filter(pk=order.pk).update(created=timezone.now() - timedelta(minutes=120))
        call_command("expire_orders")
        order.refresh_from_db(); self.apple.refresh_from_db()
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(self.apple.stock, 10)

    def test_expire_leaves_paid_and_fresh_orders(self):
        self.place_card_order()
        order = Order.objects.get()
        self.assertEqual(orders.expire_unpaid_card_orders(), 0)  # still fresh
        payment, data = self.charge(order)
        orders.mark_paid(payment.reference, data["amount"], "NGN")
        Order.objects.filter(pk=order.pk).update(created=timezone.now() - timedelta(minutes=500))
        self.assertEqual(orders.expire_unpaid_card_orders(), 0)  # paid

    def test_payment_after_expiry_revives_order(self):
        self.place_card_order(qty=3)
        order = Order.objects.get()
        orders.cancel_unpaid(order)
        payment, data = self.charge(order)
        orders.mark_paid(payment.reference, data["amount"], "NGN")
        order.refresh_from_db(); self.apple.refresh_from_db()
        self.assertTrue(order.paid)
        self.assertEqual(order.status, "confirmed")
        self.assertEqual(self.apple.stock, 7)

    def test_duplicate_payment_alerts_shop(self):
        self.place_card_order()
        order = Order.objects.get()
        payment, data = self.charge(order)
        orders.mark_paid(payment.reference, data["amount"], "NGN")
        second = Payment.objects.create(order=order, reference="dup-ref")
        with self.captureOnCommitCallbacks(execute=True):
            orders.mark_paid("dup-ref", data["amount"], "NGN")
        self.assertTrue(any("Duplicate payment" in m.subject for m in mail.outbox))
