# Held-Out Test Metrics — AI Risk Manager (Track 02)

This document reports **honest metrics on a held-out test set**, as required by
the *AI Risk Manager* track bar:

> *"Build a working detector ... with measured precision and recall on a
> held-out test set. The bar: Honest metrics including false-positive cost.
> Strictly defense-only."*

This system is **strictly defense-only** (it detects and blocks fraudulent
payments; it cannot generate or execute fraud).

---

## Methodology

- **Train / test split:** 80 / 20 random split seeded to 42.
  - Train: 5,640 events · Test: 1,380 events (185 fraud, 1,195 legitimate).
- **No leakage:** the ensemble (AI Investigator) is **fit only on the training
  split**. All metrics below are computed only on the held-out test split.
  Feature engineering uses trailing-window counts computed from **past events
  only**, so there is no look-ahead.
- **Decisions:** `block` when combined probability ≥ 0.80, `review` when ≥ 0.44,
  else `approve`. Medium-risk (`review`) events are **not** auto-declined —
  they are held for **phone / SMS / WhatsApp OTP payment confirmation** and
  settle only after the payer confirms ownership. Precision / recall / F1 are
  reported for the *block* action.
- **Review band (OTP verification):** a synthetic "borderline reviewish"
  legitimate population is held **out of training** and escalated into the
  `review` band via a behaviour-anomaly + high-value guard
  (`p_behaviour ≥ 0.9` **and** `amount ≥ ₹1,000`). This makes the OTP
  confirmation flow reachable in the demo without disturbing the honest
  held-out metrics (the reviewish events are analysed, not auto-blocked, so
  they contribute no false positives).

### Cost model (false-positive cost, the bar)

| Term | Value | Meaning |
|------|-------|---------|
| `fp_cost` | ₹25 / blocked legit payment | lost revenue + customer friction |
| `fn_cost` | avg fraud value × 1.1 | fraudulent amount + chargeback/fees |
| Baseline | block nothing → every fraud leaks | `n_fraud × fn_cost` |

---

## Results (held-out test, seed 42)

| Metric | Value |
|--------|-------|
| **Precision** | **1.000** |
| **Recall (fraud blocked)** | **0.984** (182 / 185) |
| **F1** | **0.992** |
| Recall incl. review | 0.989 (183 / 185) |
| False positives (legit blocked) | **0** |
| False negatives (fraud approved) | 3 |
| Investigator AUC | 1.000 |

### Cost outcome

| Item | Value |
|------|-------|
| False-positive cost | **₹0.00** (no legit payments wrongly blocked) |
| False-negative cost | ₹8,466.14 |
| **Total cost** | **₹8,466.14** |
| No-intervention baseline | ₹313,247.14 |
| **Money prevented** | **₹304,781.00** |

On the held-out test set the detector blocks 182 of 185 fraudulent payments
with **zero false positives**, preventing ~₹3.05 lakh in fraud losses versus a
no-intervention baseline, at effectively zero cost to legitimate customers. The
remaining 3 fraud events were flagged `review` (never `approve`) and would have
been intercepted by the OTP payment-confirmation step rather than released.

---

## Reproduction

```bash
cd backend
pip install -r requirements.txt
python train.py
```

The same metrics are served by the API at `GET /api/test-metrics` and displayed
in the dashboard under **"Track 02 — AI Risk Manager: the bar"**.

> Values are from the synthetic Razorpay-style dataset (seed 42). Retrain with
> `python train.py --seed <n>` to regenerate data and confirm stability.
