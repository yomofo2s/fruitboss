import json
import logging

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import orders, paystack
from .cart import Cart, toggle_wishlist, wishlist_ids
from .forms import CheckoutForm, ContactForm, SubscribeForm
from .models import Category, Order, Payment, Product, Subscriber

SORTS = {
    "newest": ("Newest", "-created"),
    "price_asc": ("Price: low to high", "price"),
    "price_desc": ("Price: high to low", "-price"),
    "name": ("Name A-Z", "name"),
}
PAGE_SIZE = 12
log = logging.getLogger(__name__)


def _active():
    return Product.objects.filter(is_active=True).select_related("category")


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _safe_next(request, fallback):
    nxt = request.POST.get("next", "")
    ok = url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()},
                                         require_https=request.is_secure())
    return nxt if ok else fallback


def home(request):
    products = list(_active().filter(featured=True)[:8]) or list(_active()[:8])
    return render(request, "store/home.html", {
        "products": products,
        "categories": Category.objects.all()[:4],
        "deal": _active().filter(sale_price__isnull=False, stock__gt=0).order_by("-created").first(),
    })


def shop(request):
    qs = _active()
    category = None
    slug = request.GET.get("category", "")
    if slug:
        category = get_object_or_404(Category, slug=slug)
        qs = qs.filter(category=category)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(category__name__icontains=q))
    sort = request.GET.get("sort", "newest")
    if sort not in SORTS:
        sort = "newest"
    qs = qs.order_by(SORTS[sort][1], "name")
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "store/shop.html", {
        "page": page, "categories": Category.objects.all(), "category": category,
        "q": q, "sort": sort, "sorts": [(k, v[0]) for k, v in SORTS.items()],
        "querystring": params.urlencode(),
    })


def product_detail(request, slug):
    product = get_object_or_404(_active(), slug=slug)
    related = _active().filter(category=product.category).exclude(pk=product.pk)[:4]
    return render(request, "store/product.html", {"product": product, "related": related})


def cart_detail(request):
    return render(request, "store/cart.html", Cart(request).summary())


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(_active(), pk=product_id)
    try:
        quantity = max(1, int(request.POST.get("quantity", 1)))
    except ValueError:
        quantity = 1
    cart = Cart(request)
    if not product.in_stock:
        ok, msg = False, f"Sorry, {product.name} is out of stock."
    else:
        wanted = cart.data.get(str(product.pk), 0) + quantity
        stored = cart.add(product, quantity)
        ok = True
        msg = f"{product.name} added to your cart."
        if stored < wanted:
            msg = f"Only {stored} x {product.name} available - cart updated to {stored}."
    if _is_ajax(request):
        return JsonResponse({"ok": ok, "message": msg, "cart_count": cart.count()}, status=200 if ok else 409)
    (messages.success if ok else messages.error)(request, msg)
    if request.POST.get("buy_now") and ok:
        return redirect("store:cart")
    return redirect(_safe_next(request, "store:cart"))


@require_POST
def cart_update(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    try:
        quantity = int(request.POST.get("quantity", 1))
    except ValueError:
        quantity = 1
    cart = Cart(request)
    stored = cart.add(product, quantity, override=True)
    if quantity > stored > 0:
        messages.warning(request, f"Only {stored} x {product.name} available.")
    return redirect("store:cart")


@require_POST
def cart_remove(request, product_id):
    Cart(request).remove(product_id)
    return redirect("store:cart")


def wishlist(request):
    ids = wishlist_ids(request)
    products = _active().filter(pk__in=ids)
    return render(request, "store/wishlist.html", {"products": products})


@require_POST
def wishlist_toggle(request, product_id):
    product = get_object_or_404(_active(), pk=product_id)
    added = toggle_wishlist(request, product.pk)
    msg = f"{product.name} {'saved to' if added else 'removed from'} your wishlist."
    if _is_ajax(request):
        return JsonResponse({"ok": True, "added": added, "message": msg,
                             "wishlist_count": len(wishlist_ids(request))})
    messages.success(request, msg)
    return redirect(_safe_next(request, "store:wishlist"))


def checkout(request):
    cart = Cart(request)
    summary = cart.summary()
    if not summary["lines"]:
        messages.info(request, "Your cart is empty.")
        return redirect("store:shop")

    form = CheckoutForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            order = orders.create_order(cart, form)
        except orders.StockError as exc:
            messages.error(request, str(exc))
            return redirect("store:cart")
        cart.clear()
        request.session["orders"] = request.session.get("orders", []) + [order.reference]
        if order.payment_method == Order.Payment.CARD:
            return _pay_or_retry_later(request, order)
        return redirect(order)
    return render(request, "store/checkout.html", {**summary, "form": form})


def _pay_or_retry_later(request, order):
    """Send the customer to Paystack; if that fails the order page offers a retry."""
    try:
        url = orders.start_payment(order, request.build_absolute_uri(reverse("store:payment_callback")))
    except paystack.PaystackError:
        log.exception("Could not start Paystack payment for %s", order.reference)
        messages.error(request, "We couldn't start the online payment. Please try again.")
        return redirect(order)
    return redirect(url)


def order_done(request, reference):
    # Only the browser session that placed the order may view it (it contains personal details).
    if reference not in request.session.get("orders", []):
        raise Http404
    order = get_object_or_404(Order.objects.prefetch_related("items"), reference=reference)
    return render(request, "store/order_done.html", {"order": order})


def about(request):
    return render(request, "store/about.html")


def contact(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        msg = form.save()
        send_mail(f"[Contact] {msg.subject}", f"From: {msg.name} <{msg.email}>\n\n{msg.message}",
                  None, [settings.SHOP["EMAIL"]], fail_silently=True)
        messages.success(request, "Thanks! Your message has been sent. We'll get back to you soon.")
        return redirect("store:contact")
    return render(request, "store/contact.html", {"form": form})


@require_POST
def subscribe(request):
    form = SubscribeForm(request.POST)
    if form.is_valid():
        _, created = Subscriber.objects.get_or_create(email=form.cleaned_data["email"].lower())
        messages.success(request, "Thanks for subscribing!" if created else "You're already subscribed.")
    else:
        messages.error(request, "Please enter a valid email address.")
    return redirect(_safe_next(request, "store:home"))


def _own_order_or_404(request, reference):
    if reference not in request.session.get("orders", []):
        raise Http404
    return get_object_or_404(Order, reference=reference)


@require_POST
def order_pay(request, reference):
    """(Re)start Paystack payment for an unpaid card order."""
    order = _own_order_or_404(request, reference)
    if (order.payment_method != Order.Payment.CARD or order.paid
            or order.status != Order.Status.PENDING or not settings.SHOP["PAYSTACK_ENABLED"]):
        return redirect(order)
    return _pay_or_retry_later(request, order)


def payment_callback(request):
    """Paystack sends the customer back here. We never trust the query string: verify with Paystack."""
    reference = request.GET.get("reference") or request.GET.get("trxref") or ""
    payment = Payment.objects.select_related("order").filter(reference=reference).first()
    if payment is None:
        raise Http404
    order = payment.order
    try:
        data = paystack.verify(reference)
    except paystack.PaystackError:
        log.exception("Could not verify Paystack payment %s", reference)
        messages.warning(request, "We couldn't confirm your payment yet. If you were charged, "
                                  "your order will be confirmed automatically within a few minutes.")
        return _after_payment(request, order)

    if data.get("status") == "success":
        if orders.mark_paid(reference, data.get("amount"), data.get("currency")):
            messages.success(request, "Payment received. Thank you!")
        else:
            messages.error(request, "We couldn't match your payment to the order. Please contact us "
                                    f"with order reference {order.reference}.")
    else:
        if data.get("status") in ("failed", "abandoned", "reversed"):
            orders.mark_failed(reference)
        messages.error(request, "Your payment was not completed. You can try again below.")
    return _after_payment(request, order)


def _after_payment(request, order):
    if order.reference in request.session.get("orders", []):
        return redirect(order)
    # Different browser/session than the one that placed the order: show a result without personal details.
    order.refresh_from_db()
    return render(request, "store/payment_result.html", {"order": order})


@csrf_exempt
@require_POST
def paystack_webhook(request):
    """Server-to-server confirmation. Set this URL in the Paystack dashboard (Settings > API Keys & Webhooks)."""
    if not paystack.valid_signature(request.body, request.headers.get("x-paystack-signature", "")):
        return HttpResponse(status=401)
    try:
        event = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)
    if event.get("event") == "charge.success":
        data = event.get("data") or {}
        orders.mark_paid(data.get("reference", ""), data.get("amount"), data.get("currency"))
    return HttpResponse(status=200)
