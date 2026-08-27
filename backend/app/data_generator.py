"""
PAYMENT EVENTS
--------------
Generates realistic Razorpay-style payment events for the buildathon demo.

We simulate two populations:
  1. Bona-fide customers (aggregate payment behaviour, occasional declines)
  2. Fraud actors, each crafted around a *known* real-world fraud vector:
       - CARD_TESTING  : small transactions across many merchants to validate
                          stolen card numbers (strikes + velocity)
       - VELOCITY_BURST: burst of high-value transactions from one payer
       - BOT_AUTOMATION: machine-like cadence, same device/token, no typing
       - COLLUSION_RING: a set of payers sharing devices/cards, cross-funding
       - STOLEN_CARD   : new device + high value, mismatched billing/shipping

Each fraudulent event gets a `fraud_vector` label so we can (a) train the
supervised ML risk model and (b) produce human-readable INVESTIGATOR evidence.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

import numpy as np
import pandas as pd

PAYMENT_METHODS = ["card", "upi", "netbanking", "wallet", "emi"]
CARD_SCHEMES = ["visa", "mastercard", "amex", "rupay", "diners"]
MERCHANTS = [
    "TechNova Store", "FreshCart Groceries", "Streamly", "GadgetHub",
    "FoodieExpress", "CloudSaaS", "TravelKite", "FashionFiesta",
    "GameByte", "AutoPartsPro", "BookWorm", "FitLife Gym",
]
CURRENCIES = ["INR"]

FRAUD_VECTORS = [
    "CARD_TESTING", "VELOCITY_BURST", "BOT_AUTOMATION",
    "COLLUSION_RING", "STOLEN_CARD",
]


@dataclass
class FraudCtx:
    """Per-actor fraud configuration so generators stay coherent."""
    vector: str
    shared_hash: str          # ties collusion ring members together
    device_ids: list[str]
    card_tail_range: tuple[int, int]
    merchants: list[str]
    time_window: tuple[int, int]
    velocity_burst: bool = False
    small_amount: bool = False


def _seed_hasher(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _pseudo_txn_id(i: int, actor: str) -> str:
    return f"pay_{_seed_hasher(str(i), actor)}".upper()


def generate_events(
    n_bona_fide: int = 6000,
    n_fraud: int = 900,
    seed: int = 42,
    fraud_mix: dict | None = None,
    n_reviewish: int = 120,
) -> pd.DataFrame:
    """Return a DataFrame of synthetic payment events.

    Mix (by weight) of the five fraud vectors. Defaults to roughly equal.

    `n_reviewish` adds a third "borderline / ambiguous" population of genuine
    payers whose current payment carries several soft risk signals (new device,
    mid/high value, occasional geo/method mismatch) but is NOT clearly fraud.
    These deliberately fall into the MEDIUM-RISK (review) band so the
    phone-call payment-confirmation flow is demonstrable end-to-end.
    """
    random.seed(seed)
    np.random.seed(seed)
    mix = fraud_mix or {v: 1 for v in FRAUD_VECTORS}

    rows: list[dict] = []

    # ------------------------------------------------------------ bona-fide
    for i in range(n_bona_fide):
        actor = f"usr_bona{i:05d}"
        card_tail = f"{random.randint(1000, 9999):04d}"
        device = f"dev_{random.randint(0, 40):03d}_{actor}"[:16]
        ts = int(np.random.randint(1_620_000_000, 1_720_000_000))
        amount = float(np.random.lognormal(mean=4.1, sigma=0.85))  # ~INR 60-1500
        rows.append(_bona_fide_row(actor, card_tail, device, ts, amount, i))

    # ----------------------------------------------- borderline (review band)
    for i in range(n_reviewish):
        actor = f"usr_rev{i:04d}"
        rows.append(_reviewish_row(actor, i))

    # ------------------------------------------------------------- fraud
    weights = np.array(list(mix.values()), dtype=np.float64)
    weights = weights / weights.sum()
    bins = np.random.multinomial(n_fraud, weights)
    for vector, count in zip(FRAUD_VECTORS, bins):
        rows.extend(_generate_fraud_actor(vector, count))

    df = pd.DataFrame(rows)
    df = df.sort_values("event_ts").reset_index(drop=True)
    df["event_id"] = [_pseudo_txn_id(i, "evt") for i in range(len(df))]
    return df


def _bona_fide_row(actor, card_tail, device, ts, amount, i) -> dict:
    method = random.choices(PAYMENT_METHODS, weights=[0.5, 0.3, 0.1, 0.08, 0.02])[0]
    declined = random.random() < 0.03  # 3% innocent declines
    risk = 0.05 if declined else random.uniform(0.005, 0.12)
    is_fraud = random.random() < 0.002

    merchant = _pick_merchant(actor, i)
    return {
        "event_id": "",
        "user_id": actor,
        "payer_email": f"{actor}@mail.com",
        "device_id": device,
        "card_last4": card_tail,
        "payment_method": method,
        "merchant": merchant,
        "amount_inr": round(amount, 2),
        "currency": "INR",
        "status": "captured" if not declined else "failed",
        "event_ts": ts,
        "card_bin_country": _pick_country(),
        "ip_geo_match": random.random() < 0.92,
        "is_international": random.random() < 0.12,
        "billing_zip": f"{random.randint(100000, 999999):06d}",
        "shipping_zip": "",
        "typing_seconds": float(np.random.uniform(4, 38)),
        "attempt_count": int(random.choices([1, 2, 3], weights=[0.85, 0.1, 0.05])[0]),
        "is_new_device": random.random() < 0.25,
        "three_ds_passed": True,
        "fraud_vector": None,
        "true_label": int(is_fraud),
    }


def _reviewish_row(actor: str, i: int) -> dict:
    """A borderline LEGITIMATE payer on the phone-verification (review) band.

    Genuine, but the current payment carries enough soft signals to warrant a
    confirm-first phone call rather than a clean auto-approve:
      * new device for this payer, OR
      * moderate-to-high value, AND/OR
      * geo / address inconsistency, OR multiple attempts.
    Crucially these are NOT the clear-cut fraud patterns (no card-testing
    micro-amounts, no bot cadence, no collusion ring), so they score in the
    medium-risk band instead of block.
    """
    method = random.choices(PAYMENT_METHODS, weights=[0.45, 0.3, 0.1, 0.1, 0.05])[0]
    amount = float(np.random.uniform(1200, 12000))
    ip_geo_match = random.random() < 0.7
    is_international = random.random() < 0.35
    is_new_device = random.random() < 0.6
    device = (f"dev_new_{actor}" if is_new_device else f"dev_known_{actor}")[:16]
    shipping_zip = ""
    if random.random() < 0.25:
        shipping_zip = f"{random.randint(100000, 999999):06d}"  # mismatch
    return {
        "event_id": "",
        "user_id": actor,
        "payer_email": f"{actor}@mail.com",
        "phone": f"+91{random.randint(7000000000, 9999999999)}",
        "device_id": device,
        "card_last4": f"{random.randint(1000, 9999):04d}",
        "payment_method": method,
        "merchant": _pick_merchant(actor, i),
        "amount_inr": round(amount, 2),
        "currency": "INR",
        "status": "captured",
        "event_ts": int(np.random.randint(1_620_000_000, 1_720_000_000)),
        "card_bin_country": _pick_country(),
        "ip_geo_match": bool(ip_geo_match),
        "is_international": bool(is_international),
        "billing_zip": f"{random.randint(100000, 999999):06d}",
        "shipping_zip": shipping_zip,
        "typing_seconds": float(np.random.uniform(1.0, 3.5)),
        "attempt_count": int(random.choices([1, 2, 3], weights=[0.6, 0.25, 0.15])[0]),
        "is_new_device": bool(is_new_device),
        "three_ds_passed": True,
        "fraud_vector": None,
        "true_label": 0,
    }


def _generate_fraud_actor(vector: str, count: int) -> list[dict]:
    rows: list[dict] = []
    actor = f"usr_fraud_{_seed_hasher(vector)}"

    # Choose a card-tail pool. Card-testing reuses ONE card_tail across hits;
    # a burst reuses a single device; a ring shares devices among members.
    ctx = FraudCtx(
        vector=vector,
        shared_hash=_seed_hasher(vector, "ring"),
        device_ids=[f"dev_fra_{random.randint(10000, 99999)}" for _ in range(4)],
        card_tail_range=(1000, 9999),
        merchants=random.sample(MERCHANTS, k=random.randint(2, 5)),
        time_window=(1_690_000_000, 1_700_000_000),
    )
    if vector == "COLLUSION_RING":
        ctx.shared_hash = _seed_hasher(vector, "ring", str(count))

    ring_member = 0
    for i in range(count):
        ts = random.randint(*ctx.time_window)
        if vector == "VELOCITY_BURST":
            ts = ctx.time_window[0] + i * random.randint(1, 4)  # seconds apart
            amount = float(np.random.uniform(900, 4200))
            device = ctx.device_ids[0]
        elif vector == "BOT_AUTOMATION":
            ts = ctx.time_window[0] + i * random.randint(45, 90)  # identical cadence
            amount = float(np.random.uniform(85, 240))
            device = ctx.device_ids[0]
        elif vector == "CARD_TESTING":
            ts = ctx.time_window[0] + i * random.randint(8, 40)
            amount = float(np.random.uniform(1.0, 12.0))  # tiny
            device = ctx.device_ids[i % len(ctx.device_ids)]
        elif vector == "COLLUSION_RING":
            ring_member = (ring_member + random.randint(1, 3)) % max(1, len(ctx.device_ids))
            device = ctx.device_ids[ring_member % len(ctx.device_ids)]
            amount = float(np.random.uniform(300, 2600))
            ts = ctx.time_window[0] + random.randint(0, 60 * 60 * 72)
        else:  # STOLEN_CARD
            amount = float(np.random.uniform(1200, 6800))
            device = f"dev_fra_{random.randint(11111, 99999)}"  # fresh device per event
            ts = ctx.time_window[0] + random.randint(0, 60 * 60 * 6)

        merchant = random.choice(ctx.merchants if ctx.merchants else MERCHANTS)
        card_tail = f"{random.randint(*ctx.card_tail_range):04d}"
        if vector == "CARD_TESTING":
            card_tail = f"{random.randint(1000, 9999):04d}"
            card_used = f"{random.randint(1000, 9999):04d}"  # same stolen bin family
        rows.append(
            _fraud_row(ctx, vector, actor, card_tail, device, ts, amount,
                       merchant, i, ring_member)
        )
    return rows


def _fraud_row(ctx: FraudCtx, vector, actor, card_tail, device, ts,
               amount, merchant, i, ring_member) -> dict:
    declined = random.random() < 0.45  # fraud often fails first, retries
    method = "card" if vector in ("STOLEN_CARD", "CARD_TESTING") else \
        random.choices(PAYMENT_METHODS, weights=[0.7, 0.15, 0.05, 0.05, 0.05])[0]

    is_international = vector == "STOLEN_CARD" and random.random() < 0.6
    ip_geo_match = not is_international and not (vector == "STOLEN_CARD" and random.random() < 0.4)
    billing_zip = f"{random.randint(100000, 999999):06d}"
    shipping_zip = billing_zip
    if vector == "STOLEN_CARD":
        shipping_zip = f"{random.randint(100000, 999999):06d}"  # mismatch
    is_new_device = vector == "STOLEN_CARD"

    typing_seconds = float(np.random.uniform(0.5, 3.0)) if vector == "BOT_AUTOMATION" \
        else float(np.random.uniform(1.5, 9.0))

    return {
        "event_id": "",
        "user_id": actor,
        "payer_email": f"{actor}@fraud.net",
        "device_id": device,
        "card_last4": card_tail,
        "payment_method": method,
        "merchant": merchant,
        "amount_inr": round(amount, 2),
        "currency": "INR",
        "status": "captured" if not declined else "failed",
        "event_ts": ts,
        "card_bin_country": _pick_country(),
        "ip_geo_match": bool(ip_geo_match),
        "is_international": bool(is_international),
        "billing_zip": billing_zip,
        "shipping_zip": shipping_zip,
        "typing_seconds": typing_seconds,
        "attempt_count": int(random.randint(1, 4)),
        "is_new_device": bool(is_new_device),
        "three_ds_passed": bool(random.random() < 0.5),
        "fraud_vector": vector,
        "true_label": 1,
    }


def _pick_merchant(actor: str, i: int) -> str:
    return MERCHANTS[(hash(actor) + i) % len(MERCHANTS)]


def _pick_country() -> str:
    return random.choices(["IN", "US", "UK", "SG", "AE", "DE"],
                          weights=[0.6, 0.12, 0.09, 0.07, 0.07, 0.05])[0]
