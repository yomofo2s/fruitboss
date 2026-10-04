import secrets
from decimal import Decimal

from django.db import models
from django.urls import reverse
from django.utils.text import slugify


def _unique_slug(instance, source):
    base = slugify(source) or "item"
    slug, n = base, 2
    qs = type(instance).objects.exclude(pk=instance.pk)
    while qs.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    image = models.ImageField(upload_to="categories/", blank=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(self, self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    class Unit(models.TextChoices):
        KG = "kg", "kg"
        PIECE = "piece", "piece"
        PACK = "pack", "pack"
        BASKET = "basket", "basket"
        BOTTLE = "bottle", "bottle"

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=130, unique=True, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    sale_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Optional. Must be lower than the normal price.",
    )
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.KG)
    stock = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to="products/", blank=True)
    featured = models.BooleanField(default=False, help_text="Show on the home page.")
    is_active = models.BooleanField(default=True, help_text="Untick to hide from the shop.")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(self, self.name)
        super().save(*args, **kwargs)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.sale_price is not None and self.sale_price >= self.price:
            raise ValidationError({"sale_price": "Sale price must be lower than the normal price."})

    def get_absolute_url(self):
        return reverse("store:product", args=[self.slug])

    @property
    def on_sale(self):
        return self.sale_price is not None and self.sale_price < self.price

    @property
    def current_price(self):
        return self.sale_price if self.on_sale else self.price

    @property
    def discount_percent(self):
        if not self.on_sale:
            return 0
        return int(round((1 - self.sale_price / self.price) * 100))

    @property
    def in_stock(self):
        return self.stock > 0


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        SHIPPED = "shipped", "Out for delivery"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    class Payment(models.TextChoices):
        CARD = "card", "Pay online (card, bank, USSD)"
        COD = "cod", "Pay on delivery"
        TRANSFER = "transfer", "Bank transfer"

    reference = models.CharField(max_length=12, unique=True, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    payment_method = models.CharField(max_length=10, choices=Payment.choices, default=Payment.COD)
    paid = models.BooleanField(default=False)

    full_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    notes = models.TextField(blank=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=12, decimal_places=2)

    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"Order {self.reference}"

    def save(self, *args, **kwargs):
        if not self.reference:
            while True:
                ref = "FB" + secrets.token_hex(4).upper()
                if not Order.objects.filter(reference=ref).exists():
                    self.reference = ref
                    break
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("store:order_done", args=[self.reference])


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=120)
    unit = models.CharField(max_length=10)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.quantity} x {self.name}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class Payment(models.Model):
    """One Paystack payment attempt for an order (a customer may retry after a failed attempt)."""

    class Status(models.TextChoices):
        INITIATED = "initiated", "Initiated"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    reference = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.INITIATED)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.reference} ({self.status})"


class ContactMessage(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    subject = models.CharField(max_length=160)
    message = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    handled = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.subject} - {self.name}"


class Subscriber(models.Model):
    email = models.EmailField(unique=True)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email
