"""
OPTIONAL Razorpay REAL test-mode integration.

The pipeline's default dataset is a keyless, offline, synthetic stream of
Razorpay-*style* payment events (see app/data_generator.py). This module adds
the ability to plug in your OWN Razorpay **test-mode** keys (rzp_test_*) and:

  * create a real test order via the Razorpay Orders API,
  * ingest a real `payment.captured` webhook and run it through the full
    fraud-detection pipeline (scores + evidence + decision).

SECURITY
--------
Never hard-code keys. Provide them via environment variables:

    RAZORPAY_KEY_ID=rzp_test_xxxxxxxx
    RAZORPAY_KEY_SECRET=xxxxxxxx

or a local `.env` file (NOT committed). If neither is present the module
reports "not configured" and the real-integration endpoints return a helpful
message instead of failing.
"""

from __future__ import annotations

import os

import razorpay

from app.data_generator import FRAUD_VECTORS


def load_dotenv():
    """Minimal dotenv loader (avoids a hard dependency)."""
    path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_dotenv()


def is_configured() -> bool:
    return bool(os.getenv("RAZORPAY_KEY_ID") and os.getenv("RAZORPAY_KEY_SECRET"))


def client() -> razorpay.Client:
    key = os.getenv("RAZORPAY_KEY_ID")
    secret = os.getenv("RAZORPAY_KEY_SECRET")
    return razorpay.Client(auth=(key, secret))


def create_test_order(amount_inr: float, receipt: str = "buildathon_demo",
                      currency: str = "INR") -> dict:
    """Create a real test order. amount must be in paise. Returns order dict."""
    if not is_configured():
        raise RuntimeError(
            "Razorpay test keys not configured. Set RAZORPAY_KEY_ID and "
            "RAZORPAY_KEY_SECRET (rzp_test_*) or add them to backend/.env"
        )
    c = client()
    data = {
        "amount": int(round(amount_inr * 100)),
        "currency": currency,
        "receipt": receipt,
        "notes": {"source": "razorpay-fraud-guardian-demo"},
    }
    return c.order.create(data=data)


def webhook_event_to_payload(webhook: dict) -> dict:
    """Map a Razorpay payment.captured webhook payload -> pipeline payment event."""
    payment = webhook.get("payload", {}).get("payment", {}).get("entity", {})
    order = webhook.get("payload", {}).get("order", {}).get("entity", {}) or {}
    notes = order.get("notes", {}) or {}

    last4 = "0000"
    card = payment.get("card", {}) or {}
    if card:
        last4 = str(card.get("last4") or "0000")
    bin_country = (card.get("issuer_country") or "IN")[:2].upper()

    billing_zip = str(notes.get("billing_zip") or "400001")[-6:]
    shipping_zip = str(notes.get("shipping_zip") or billing_zip)[-6:]

    return {
        "user_id": payment.get("email") or payment.get("contact") or "rzp_user",
        "device_id": f"rzp:{payment.get('id', 'device')}",
        "card_last4": last4,
        "amount_inr": (payment.get("amount") or 0) / 100.0,
        "currency": payment.get("currency") or "INR",
        "payment_method": payment.get("method") or "card",
        "merchant": notes.get("merchant") or "Razorpay Test Store",
        "card_bin_country": bin_country,
        "ip_geo_match": (bin_country == "IN"),
        "is_international": (bin_country != "IN"),
        "billing_zip": billing_zip,
        "shipping_zip": shipping_zip,
        "typing_seconds": 12.0,
        "attempt_count": int(payment.get("error_reason") or 1),
        "is_new_device": bool(payment.get("error_reason")),
        "three_ds_passed": True,
        "status": "captured",
    }


def _card_test_hit(i: int) -> dict:
    """A single low-value card-testing attempt from the same bot device."""
    return {
        "user_id": "usr_demo_mallory",
        "device_id": "dev_demo_bot_0042",
        "card_last4": "4242",
        "amount_inr": round(1.5 + i, 2),       # micro-amount probing
        "merchant": "GameByte",
        "payment_method": "card",
        "card_bin_country": "US",
        "ip_geo_match": False,
        "is_international": True,
        "billing_zip": "100001",
        "shipping_zip": "900001",
        "typing_seconds": 0.4,                 # machine-fast
        "attempt_count": 1,
        "is_new_device": True,
        "three_ds_passed": False,
        "status": "failed",
    }


def demo_payment_for_testing() -> dict:
    """A ready-made 'card testing' demo. Returns the batch body for
    POST /api/investigate: a stream of micro card-test attempts from a bot
    device, followed by the target (a slightly larger charge on the same
    stolen card). With this velocity context the pipeline blocks it."""
    target = _card_test_hit(11)
    target["amount_inr"] = 45.0
    target["status"] = "captured"
    history = [_card_test_hit(i) for i in range(6)]
    return {"event": target, "history": history}


def demo_clean_payment() -> dict:
    """A benign, established customer — should be approved."""
    return {
        "user_id": "usr_bona00333",
        "device_id": "dev_clean_0033",
        "card_last4": "8123",
        "amount_inr": 640.0,
        "merchant": "FreshCart Groceries",
        "payment_method": "upi",
        "card_bin_country": "IN",
        "ip_geo_match": True,
        "is_international": False,
        "billing_zip": "400001",
        "shipping_zip": "400001",
        "typing_seconds": 21.0,
        "attempt_count": 1,
        "is_new_device": False,
        "three_ds_passed": True,
        "status": "captured",
    }
