"""
FEATURE ENGINEERING
-------------------
Converts raw payment events into a numeric feature matrix that all three
downstream models consume. Features fall into natural groups:

  * TIMING / CONTEXT    : hour-of-day, weekend, time-only features
  * AMOUNT              : absolute value plus per-user statistics (z-score)
  * CARD / DEVICE       : reuse frequency, newness, attempts
  * VELOCITY (AGGREGATE): rolling counts/sums over trailing windows keyed by
                          user, card-last4, device, IP-bucket, merchant
  * BEHAVIOUR           : typing cadence, method mix entropy, flag patterns
  * COUNTRY/GEO          : international + billing/shipping mismatch

Velocity features are computed per-event with a *trailing window* (only past
events per key are counted) to avoid look-ahead leakage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TIME_MS = 1_000_000_000  # timestamps are in nanoseconds in the raw events


class FeatureEngineer:
    def __init__(self, window_seconds: int = 3600, long_window_seconds: int = 86400):
        self.window = window_seconds
        self.long_window = long_window_seconds

    def build(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ts_sec"] = (df["event_ts"] / TIME_MS).astype("int64")
        df["ts_dt"] = pd.to_datetime(df["event_ts"], unit="ns")

        f = pd.DataFrame(index=df.index)

        # ---- ensure newer (non-card) signature columns exist with safe defaults
        for col, default in [
            ("is_refund", False), ("refund_session", False),
            ("new_beneficiary", False), ("account_reset", False),
            ("payout_via", "card"),
        ]:
            if col not in df.columns:
                df[col] = default
            if df[col].dtype == object:
                df[col] = df[col].where(df[col].notna(), default).astype(object)
            else:
                df[col] = df[col].fillna(default)

        # ---- context / timing
        f["hour"] = df["ts_dt"].dt.hour
        f["is_weekend"] = (df["ts_dt"].dt.weekday >= 5).astype(int)
        f["is_night"] = (((f["hour"] >= 22) | (f["hour"] <= 5))).astype(int)

        # ---- amount
        amt = df["amount_inr"].astype(float)
        f["amount"] = amt
        f["amount_log"] = np.log1p(amt)
        f["amount_round"] = (amt % 1 == 0).astype(int)          # bots round amounts
        f["amount_suspicious"] = ((amt >= 1000) & (amt <= 5000)).astype(int)

        # ---- card / device
        f["is_new_device"] = df["is_new_device"].astype(int)
        f["attempt_count"] = df["attempt_count"].astype(int)
        f["attempts_gt_1"] = (df["attempt_count"] > 1).astype(int)
        f["three_ds_passed"] = df["three_ds_passed"].astype(int)

        # ---- geo
        f["is_international"] = df["is_international"].astype(int)
        f["ip_geo_mismatch"] = (1 - df["ip_geo_match"]).astype(int)
        f["billing_shipping_mismatch"] = (
            df["billing_zip"].ne(df["shipping_zip"])
        ).astype(int)

        # ---- behaviour
        f["typing_seconds"] = df["typing_seconds"].astype(float)
        f["typing_very_fast"] = (df["typing_seconds"] < 2.0).astype(int)

        # ---- velocity features (trailing window, no leakage)
        ts = df["ts_sec"]
        for label, key in [
            ("user", df["user_id"]),
            ("card", df["card_last4"]),
            ("device", df["device_id"]),
            ("merchant", df["merchant"].astype(str)),
        ]:
            f[f"count_{label}_{self.window // 60}m"] = _rolling_count(
                ts, key, self.window
            )
            f[f"amount_{label}_{self.window // 60}m"] = _rolling_sum(
                ts, key, self.window, amt
            )

        # long-window user velocity
        f[f"count_user_{self.long_window // 3600}h"] = _rolling_count(
            ts, df["user_id"], self.long_window
        )
        f[f"amount_user_{self.long_window // 3600}h"] = _rolling_sum(
            ts, df["user_id"], self.long_window, amt
        )

        # card family reuse == card testing signature
        f["card_device_combo_reuse"] = _rolling_count(
            ts, df["device_id"].astype(str) + "|" + df["card_last4"], self.window
        )

        # ---- derived flags that make rules interpretable
        f["velocity_flag"] = (f[f"count_card_{self.window // 60}m"] >= 4).astype(int)
        f["bot_cadence_flag"] = (
            (f["typing_seconds"] < 2.0)
            & (f["amount_round"] == 1)
            & (f["is_night"] == 1)
        ).astype(int)
        f["geography_flag"] = (
            (f["is_international"] == 1) | (f["billing_shipping_mismatch"] == 1)
        ).astype(int)
        f["card_test_flag"] = (
            (f["amount"] <= 15) & (f["count_card_60m"] >= 3)
        ).astype(int)

        # ---- derived flags for the newer (non-card) fraud signatures
        f["upi_flag"] = (df["payment_method"] == "upi").astype(int)
        f["p2p_new_beneficiary"] = ((df["payment_method"].isin(["upi", "wallet"]))
                                    & (df["new_beneficiary"] == 1)).astype(int)
        f["refund_flag"] = df["is_refund"].astype(int)
        f["refund_session_flag"] = df["refund_session"].astype(int)
        f["account_reset_flag"] = df["account_reset"].astype(int)
        f["ato_flag"] = (
            (df["account_reset"] == 1)
            & (f["is_new_device"] == 1)
            & (f["amount_suspicious"] == 0)
            & (f["amount"] >= 5000)
        ).astype(int)
        # merchant/BIN concentration: how much of this payer's recent activity
        # is pinned on a single merchant -> signals merchant/BIN bust-out
        f["merchant_concentration"] = (
            f[f"count_merchant_{self.window // 60}m"]
            / f[f"count_user_{self.window // 60}m"].clip(lower=1)
        ).round(3)
        f["merchant_flag"] = (
            (f[f"count_merchant_{self.window // 60}m"] >= 4)
            & (f["merchant_concentration"] >= 0.9)
        ).astype(int)

        # ---- behaviour entropy: how varied is the user's method mix
        f["method_mix_entropy"] = _method_entropy(df)
        f["recent_failure_rate"] = _failure_rate(df, self.window)

        # encode payment method one-hot
        for m in ["card", "upi", "netbanking", "wallet", "emi"]:
            f[f"method_{m}"] = (df["payment_method"] == m).astype(int)

        return f


def _rolling_count(ts: pd.Series, key: pd.Series, window: int) -> pd.Series:
    """Number of prior events for the same key within `window` seconds (no leakage)."""
    out = pd.Series(0, index=ts.index, dtype=np.int64)
    df = pd.DataFrame({"ts": ts.values, "key": key.values}).reset_index()
    df = df.sort_values("ts")
    k = df["key"].values
    t = df["ts"].values
    idx = df.index.values
    from collections import defaultdict
    seen = defaultdict(int)
    active = defaultdict(list)  # timestamps still inside window, per key
    for j in range(len(t)):
        q = active[k[j]]
        cutoff = t[j] - window
        drop = 0
        while drop < len(q) and q[drop] < cutoff:
            drop += 1
        if drop:
            del q[:drop]
            seen[k[j]] -= drop
        out.loc[idx[j]] = seen[k[j]]
        seen[k[j]] += 1
        q.append(t[j])
    return out


def _rolling_sum(ts: pd.Series, key: pd.Series, window: int, amt: pd.Series) -> pd.Series:
    """Cumulative sum of `amt` for the same key within `window` seconds (no leakage)."""
    out = pd.Series(0.0, index=ts.index, dtype=np.float64)
    df = pd.DataFrame({
        "ts": ts.values, "key": key.values, "amt": amt.values,
    }).reset_index()
    df = df.sort_values("ts")
    from collections import defaultdict
    active = defaultdict(list)  # list of [timestamp, amount]
    k = df["key"].values
    t = df["ts"].values
    a = df["amt"].values
    idx = df.index.values
    running = defaultdict(float)
    for j in range(len(t)):
        q = active[k[j]]
        cutoff = t[j] - window
        drop = 0
        while drop < len(q) and q[drop][0] < cutoff:
            running[k[j]] -= q[drop][1]
            drop += 1
        if drop:
            del q[:drop]
        out.loc[idx[j]] = running[k[j]]
        running[k[j]] += a[j]
        q.append((t[j], a[j]))
    return out


def _failure_rate(df: pd.DataFrame, window: int) -> pd.Series:
    """Rate of failed events per user in trailing window."""
    ts = (df["event_ts"] / TIME_MS).astype("int64")
    fail = (df["status"] == "failed").astype(int)
    return _rolling_sum(ts, df["user_id"], window, fail) / \
        _rolling_count(ts, df["user_id"], window).clip(lower=1)


def _method_entropy(df: pd.DataFrame) -> pd.Series:
    """Shannon entropy of each user's payment-method distribution so far."""
    from collections import defaultdict
    out = pd.Series(0.0, index=df.index, dtype=np.float64)
    hist = defaultdict(lambda: defaultdict(int))
    for i, (uid, method) in enumerate(zip(df["user_id"], df["payment_method"])):
        h = hist[uid]
        h[method] = h.get(method, 0) + 1
        total = sum(h.values())
        ent = -sum((c / total) * np.log(c / total) for c in h.values())
        out.iloc[i] = ent
    return out
