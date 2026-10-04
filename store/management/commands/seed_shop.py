"""Load starter categories and products using the template's bundled photos.

Safe to re-run: existing products (matched by name) are left untouched.
Replace the images and prices from the admin (/admin/) once you have real photos.
"""
from decimal import Decimal

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from store.models import Category, Product

IMAGES = settings.BASE_DIR / "static" / "images"

CATEGORIES = [
    ("Fruits", "category-1.jpg"),
    ("Vegetables", "category-2.jpg"),
    ("Juices", "category-3.jpg"),
    ("Dried", "category-4.jpg"),
]

# name, category, price, sale_price, unit, stock, featured, image
PRODUCTS = [
    ("Strawberry", "Fruits", 2500, None, "pack", 40, True, "product-2.jpg"),
    ("Apple", "Fruits", 3000, None, "kg", 60, True, "product-10.jpg"),
    ("Tomato", "Vegetables", 1500, 1100, "kg", 80, True, "product-5.jpg"),
    ("Fruit Juice", "Juices", 1800, None, "bottle", 50, True, "product-8.jpg"),
    ("Bell Pepper", "Vegetables", 2000, 1400, "kg", 45, True, "product-1.jpg"),
    ("Green Beans", "Vegetables", 1800, None, "kg", 30, False, "product-3.jpg"),
    ("Purple Cabbage", "Vegetables", 1200, None, "piece", 25, False, "product-4.jpg"),
    ("Broccoli", "Vegetables", 2200, None, "kg", 20, False, "product-6.jpg"),
    ("Carrots", "Vegetables", 1000, None, "kg", 70, False, "product-7.jpg"),
    ("Onion", "Vegetables", 900, 700, "kg", 90, False, "product-9.jpg"),
    ("Garlic", "Dried", 2800, None, "pack", 35, False, "product-11.jpg"),
    ("Chilli", "Dried", 1600, None, "pack", 55, False, "product-12.jpg"),
]


def attach(obj, filename):
    with open(IMAGES / filename, "rb") as fh:
        obj.image.save(filename, File(fh), save=True)


class Command(BaseCommand):
    help = "Seed starter categories and products."

    def handle(self, *args, **options):
        cats = {}
        for name, img in CATEGORIES:
            cat, created = Category.objects.get_or_create(name=name)
            if created:
                attach(cat, img)
            cats[name] = cat

        made = 0
        for name, cat, price, sale, unit, stock, featured, img in PRODUCTS:
            if Product.objects.filter(name=name).exists():
                continue
            p = Product.objects.create(
                category=cats[cat], name=name, price=Decimal(price),
                sale_price=Decimal(sale) if sale else None, unit=unit, stock=stock, featured=featured,
                description=f"Fresh {name.lower()}, carefully packed and delivered to your door.",
            )
            attach(p, img)
            made += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {made} new product(s)."))
