from django.contrib import admin

from . import orders
from .models import Category, ContactMessage, Order, OrderItem, Payment, Product, Subscriber


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "sale_price", "unit", "stock", "featured", "is_active")
    list_filter = ("category", "featured", "is_active")
    list_editable = ("price", "sale_price", "stock", "featured", "is_active")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("product", "name", "unit", "unit_price", "quantity")

    def has_add_permission(self, request, obj=None):
        return False


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    readonly_fields = ("reference", "status", "created")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "full_name", "phone", "total", "payment_method", "paid", "status", "created")
    list_filter = ("status", "payment_method", "paid", "created")
    list_editable = ("status", "paid")
    search_fields = ("reference", "full_name", "email", "phone")
    readonly_fields = ("reference", "subtotal", "delivery_fee", "total", "created")
    inlines = [OrderItemInline, PaymentInline]
    actions = ["cancel_unpaid_and_restock"]

    @admin.action(description="Cancel selected unpaid orders and return stock")
    def cancel_unpaid_and_restock(self, request, queryset):
        done = sum(orders.cancel_unpaid(o) for o in queryset)
        self.message_user(request, f"Cancelled {done} order(s); paid or non-pending orders were left alone.")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "name", "email", "created", "handled")
    list_filter = ("handled",)
    list_editable = ("handled",)
    readonly_fields = ("name", "email", "subject", "message", "created")


admin.site.register(Subscriber)
