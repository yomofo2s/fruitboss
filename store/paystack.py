"""Minimal Paystack client (stdlib only). https://paystack.com/docs/api/"""
import hashlib
import hmac
import json
import urllib.error
import urllib.request

from django.conf import settings

API = "https://api.paystack.co"


class PaystackError(Exception):
    pass


def to_kobo(amount):
    return int(round(amount * 100))


def _request(method, path, payload=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                 "Content-Type": "application/json", "User-Agent": "Fruitboss/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            msg = json.load(exc).get("message", "")
        except ValueError:
            msg = ""
        raise PaystackError(f"Paystack returned HTTP {exc.code}: {msg}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise PaystackError(f"Could not reach Paystack: {exc}") from exc
    if not body.get("status"):
        raise PaystackError(body.get("message", "Paystack request failed"))
    return body["data"]


def initialize(*, email, amount_kobo, reference, callback_url, metadata=None):
    """Returns Paystack's data dict (authorization_url, access_code, reference)."""
    return _request("POST", "/transaction/initialize", {
        "email": email, "amount": amount_kobo, "currency": "NGN", "reference": reference,
        "callback_url": callback_url, "metadata": metadata or {},
    })


def verify(reference):
    """Returns Paystack's transaction data (status, amount, currency, reference, ...)."""
    return _request("GET", f"/transaction/verify/{reference}")


def valid_signature(raw_body, signature):
    expected = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), raw_body, hashlib.sha512).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, signature)
