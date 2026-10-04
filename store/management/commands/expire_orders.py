"""Cancel unpaid Paystack orders and return their stock. Run every few minutes (cron / scheduler)."""
from django.core.management.base import BaseCommand

from store import orders


class Command(BaseCommand):
    help = "Cancel unpaid online-payment orders older than SHOP['UNPAID_ORDER_MINUTES'] and restock them."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=None)

    def handle(self, *args, **options):
        n = orders.expire_unpaid_card_orders(options["minutes"])
        self.stdout.write(f"Cancelled {n} unpaid order(s).")
