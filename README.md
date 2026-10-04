# Fruitboss

Online fruit shop for [fruitbossng.com](https://fruitbossng.com): a Django app on top of the Vegefoods (Colorlib) front-end template.

## Features

- Catalogue with categories, search, sorting, pagination, sale prices and stock levels
- Session cart (no login needed) with stock checks, free-delivery threshold and wishlist
- Add-to-cart / wishlist without page reloads (falls back to normal form posts without JS)
- Checkout with order confirmation emails (customer + shop): pay online with Paystack (card, bank, USSD), pay on delivery, or bank transfer
- Admin at `/admin/` for products, categories, orders (status, paid), contact messages, subscribers
- Responsive (phone to desktop); product actions stay visible on touch screens

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DJANGO_DEBUG=1
python manage.py migrate
python manage.py seed_shop        # starter products, using the template photos
python manage.py createsuperuser
python manage.py runserver
python manage.py test
```

Open http://127.0.0.1:8000/ and manage stock and prices at http://127.0.0.1:8000/admin/.
Emails print to the console unless `EMAIL_HOST` is set.

## Configuration (environment variables)

See `.env.example`. In production (`DJANGO_DEBUG` unset) `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS` are required.
Shop settings (delivery fee, free-delivery threshold, bank details, contact info) live in `SHOP` in `fruitbossng/settings.py`.

## Paystack (online payments)

1. Get your keys at https://dashboard.paystack.com/#/settings/developers and set `PAYSTACK_SECRET_KEY` (`sk_test_...` to try it, `sk_live_...` for real money). Without a key the "Pay online" option is hidden.
2. In the Paystack dashboard (Settings > API Keys & Webhooks) set the **webhook URL** to `https://<your-domain>/payments/paystack/webhook/`. The webhook confirms payments even if the customer closes the browser before returning to the site.
3. Run `python manage.py expire_orders` every few minutes (cron/scheduler). Unpaid online orders hold their stock; this cancels them after `SHOP_UNPAID_ORDER_MINUTES` (default 60) and puts the stock back.

How it works: checkout creates the order (stock reserved) and sends the customer to Paystack. On return we **verify the transaction with Paystack** (never trusting the URL), check the amount and currency match the order, then mark it paid and send the confirmation emails. The callback and webhook can both fire safely. A customer who abandons payment can retry from the order page. Each attempt is stored under the order in the admin (Payments). If a payment arrives after the order was auto-cancelled, the order is revived and you're emailed to check stock; duplicate payments also email you so you can refund in the Paystack dashboard.

## Deploying

```bash
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
gunicorn fruitbossng.wsgi
```

Static files are served by WhiteNoise. **Uploaded product photos live in `MEDIA_ROOT`**, which Django only serves in
development: in production put it on a persistent disk behind your web server (or move to object storage), and use a
real database (the default is SQLite) if you run more than one instance.

## Not included yet

Customer accounts / order history, refunds from within the admin (use the Paystack dashboard), and the blog pages from the original template.
