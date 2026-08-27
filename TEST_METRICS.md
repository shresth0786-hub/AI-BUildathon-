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
  - Train: 5,520 events · Test: 1,380 events (180 fraud, 1,200 legitimate).
- **No leakage:** the ensemble (AI Investigator) is **fit only on the training
  split**. All metrics below are computed only on the held-out test split.
  Feature engineering uses trailing-window counts computed from **past events
  only**, so there is no look-ahead.
- **Decisions:** `block` when combined probability ≥ 0.80, `review` when ≥ 0.44,
  else `approve`. Precision / recall / F1 are reported for the *block* action.

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
| **Recall (fraud blocked)** | **0.994** (179 / 180) |
| **F1** | **0.997** |
| Recall incl. review | 0.994 |
| False positives (legit blocked) | **0** |
| False negatives (fraud approved) | 1 |
| Investigator AUC | 0.998 |

### Cost outcome

| Item | Value |
|------|-------|
| False-positive cost | **₹0.00** (no legit payments wrongly blocked) |
| False-negative cost | ₹1,478.31 |
| **Total cost** | **₹1,478.31** |
| No-intervention baseline | ₹266,096.64 |
| **Money prevented** | **₹264,618.33** |

On the held-out test set the detector blocks 179 of 180 fraudulent payments
with **zero false positives**, preventing ~₹2.6 lakh in fraud losses versus a
no-intervention baseline, at effectively zero cost to legitimate customers.

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
