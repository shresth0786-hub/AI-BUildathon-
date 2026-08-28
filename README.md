# Razorpay Fraud Guardian

An **end-to-end AI fraud-detection system** built for the Razorpay buildathon,
submitted under **Track 02 — AI Risk Manager** (a working detector with
**honest precision/recall and false-positive cost on a held-out test set**;
strictly **defense-only**). It mirrors the reference architecture:

```
RAZORPAY TEST PAYMENTS → Feature Engineering
  → [ ML Risk Model | Behaviour AI | Graph Engine ]   (parallel)
  → AI Investigator  →  Decision + Evidence
  → React Dashboard
```

Three independent models score every payment in parallel; an **AI Investigator**
ensembles them into one calibrated fraud probability, decides **approve / review /
block**, and generates a **human-readable investigation report with evidence**.

---

## Quick start

Requires **Python 3.10+** and **Node 18+**.

```bash
# 1. Install backend deps
cd backend
pip install -r requirements.txt

# 2. (one-time) Train on synthetic Razorpay-style data and save artifacts
python train.py

# 3. Start the API
uvicorn app.main:app --port 8100

# 4. In a second terminal, start the dashboard
cd frontend/app
npm install
npm run dev
```

Open **http://localhost:5173** (dashboard) and **http://127.0.0.1:8100/docs** (API docs).

> Note: the dashboard's Vite dev server proxies `/api` → `http://127.0.0.1:8100`.
> If you run the API on a different port, update `frontend/app/vite.config.js`.

Or, on Windows, run `powershell -ExecutionPolicy Bypass -File start.ps1` to launch both.

---

## What each component does

### 1. Payment events — `backend/app/data_generator.py`
Generates realistic Razorpay-style events driven by `seed`. Bona-fide customers
are interleaved with fraud actors, each engineered around a **known real-world
fraud vector** so the demo is meaningful and explainable:

| Vector             | Pattern                                                                |
|--------------------|------------------------------------------------------------------------|
| `CARD_TESTING`     | many tiny transactions to validate stolen card numbers                 |
| `VELOCITY_BURST`   | burst of high-value charges from one payer                             |
| `BOT_AUTOMATION`   | machine-cadence, fast typing, same device/card                         |
| `COLLUSION_RING`   | a set of payers sharing devices/cards and cross-funding                |
| `STOLEN_CARD`      | new device + high value + billing/shipping mismatch                    |

### 2. Feature engineering — `backend/app/features.py`
Converts raw events into a numeric matrix with **leak-safe trailing-window**
velocity features (counts/sums per user, card, device, merchant over 1h/24h),
plus timing, amount, card/device, geographic and behavioural (typing cadence,
method-mix entropy, failure rate) signals.

### 3. The three models — `backend/app/models/`
| Model                | Approach                                                            |
|----------------------|---------------------------------------------------------------------|
| `ml_risk.py`         | Supervised gradient-boosted classifier (XGBoost) + Platt calibration → `p_ml` |
| `behaviour_ai.py`    | Unsupervised under-complete autoencoder trained on legit-only behaviour → reconstruction-anomaly `p_behav` |
| `graph_engine.py`    | Heterogeneous payer/card/device graph + influence propagation from confirmed-fraud seeds → `p_graph` |

### 4. AI Investigator — `backend/app/investigator.py`
- Logistic ensemble over `[p_ml, p_behav, p_graph]` → calibrated fraud probability.
- Decision thresholds tuned to a target fraud leakage; a light classifier predicts
  the most likely **fraud vector**.
- Builds an **evidence list** (which model fired and why — velocity, geography,
  bot cadence, shared-entity linkage, ensemble agreement) and a narrative report.
- **Phone-call payment confirmation:** medium-risk (`review`) payments are **not**
  auto-approved; they are held and a **phone call/OTP** is issued
  (`backend/app/verification.py`). The payment settles only after the payer
  confirms ownership (correct OTP → `approve`; wrong OTP / denied / cap exceeded
  → `block`). Ships as a **simulated** offline demo (OTP + call script shown in
  the dashboard) with an optional **real Twilio** fallback. A borderline
  "review-ish" legitimate population is held out of training and escalated into
  the `review` band (behaviour-anomaly + high-value guard) so this flow is
  demonstrable without hurting the honest held-out metrics.
- **Persistent recorded-call log:** every verification session is written to
  `backend/data/verifications.json` (gitignored) so the call log survives a
  backend restart and appears on the dashboard as "Recorded calls". In real
  Twilio mode calls are placed with `record=True` and the `call_sid` +
  recording-availability are stored, so call **audio** is captured for audit
  (a console link is shown once the Twilio account is upgraded to billing).

### 5. API + Dashboard
- **FastAPI** (`app/main.py`): summary, event stream, per-event investigation,
  fraud vectors, live `/api/investigate`, and **optional real Razorpay test-mode**
  endpoints (`/api/rzp/create-order`, `/api/rzp/webhook`).
- **React + Recharts** dashboard: decision distribution, model-ensemble weights,
  fraud-vector breakdown, live payment check, clickable investigation reports,
  and a **phone-verification panel** (run the "Borderline — phone verify"
  scenario → see OTP + call script → confirm / deny / resend).

---

## Results (held-out test set, seed 42)

Honest metrics computed on a **held-out test split** the ensemble was never
trained on (no leakage). Full breakdown with the false-positive cost model is in
**[TEST_METRICS.md](TEST_METRICS.md)**.

| Metric | Value |
|--------|-------|
| **Precision** | **1.000** |
| **Recall (fraud blocked)** | **0.973** (180 / 185) |
| **F1** | **0.986** |
| False positives (legit blocked) | **0** |
| False negatives (fraud approved) | 5 |
| Investigator AUC | 0.998 |

Cost outcome on the test set: false-positive cost **₹0**, false-negative cost
₹8,466, **total cost ₹8,466** vs. a no-intervention baseline of ₹313,247 →
**₹304,781 money prevented**. Track split: 5,640 train / 1,380 test events
(185 fraud). The 5 honest "false negatives" were all escalated to `review`
(never `approve`), so they would have been caught by the phone-call
payment-confirmation step rather than released.

Served live at `GET /api/test-metrics` and displayed in the dashboard under
**"Track 02 — AI Risk Manager: the bar"**.

---

## Using real Razorpay test-mode keys (optional)

The default dataset is **keyless** synthetic data. To plug in *real* Razorpay test
checkouts and webhooks:

1. Copy `backend/.env.example` → `backend/.env`
2. Add your own **`rzp_test_*`** keys:
   ```
   RAZORPAY_KEY_ID=rzp_test_xxxxxx
   RAZORPAY_KEY_SECRET=xxxxxx
   ```
3. Restart the backend. Check status at `GET /api/rzp/status`.
4. Create an order: `POST /api/rzp/create-order?amount_inr=500`
5. Point your Razorpay test webhook to `POST /api/rzp/webhook` (event
   `payment.captured` / `order.paid`). Each webhook is run through the full
   pipeline and returns scores + evidence + decision.

> Kept fully optional — without keys the system still runs the complete demo
> (keyless mode). **Never commit `.env` or use live `rzp_live_*` keys.**

---

## API endpoints

| Method | Path                     | Description                              |
|--------|--------------------------|------------------------------------------|
| GET    | `/api/summary`           | Model/data summary + decision metrics    |
| GET    | `/api/test-metrics`      | Honest held-out precision/recall/F1 + cost |
| GET    | `/api/events?risk=`      | Recent payments with scores & decisions  |
| GET    | `/api/events/{id}`       | Full investigation report for one event  |
| GET    | `/api/vectors`           | Fraud-vector distribution                |
| POST   | `/api/investigate`       | Live score a payment (with optional `history`) |
| GET    | `/api/verification`      | List phone-call payment-confirmation sessions  |
| POST   | `/api/verification/{id}/confirm` | Complete the call with the payer's OTP (→ approve/block) |
| POST   | `/api/verification/{id}/deny`    | Caller denied ownership (→ block)        |
| POST   | `/api/verification/{id}/resend`  | Regenerate the OTP + re-place the call    |
| GET    | `/api/demo/fraud`        | Card-testing burst demo body             |
| GET    | `/api/demo/clean`        | Clean-customer demo body                 |
| GET    | `/api/rzp/status`        | Real-key configuration status            |
| POST   | `/api/rzp/create-order`  | Create a real Razorpay test order        |
| POST   | `/api/rzp/webhook`       | Ingest a real Razorpay webhook           |

---

## Project layout

```
razorpay-fraud-detector/
├─ backend/
│  ├─ app/
│  │  ├─ data_generator.py      # Razorpay-style events
│  │  ├─ features.py            # feature engineering
│  │  ├─ models/
│  │  │  ├─ ml_risk.py          # supervised risk scorer
│  │  │  ├─ behaviour_ai.py     # anomaly autoencoder
│  │  │  └─ graph_engine.py     # network graph model
│  │  ├─ investigator.py        # ensemble + evidence
│  │  ├─ verification.py        # phone-call payment confirmation (OTP)
│  │  ├─ pipeline.py            # orchestration
│  │  ├─ razorpay_client.py     # optional real-key integration
│  │  └─ main.py                # FastAPI
│  ├─ train.py                  # train + save artifacts
│  ├─ requirements.txt
│  └─ .env.example
├─ frontend/
│  └─ app/                      # React (Vite) dashboard
│     └─ src/App.jsx
├─ start.ps1                    # launch both (Windows)
└─ README.md
```

Run `python train.py` any time with different `--n-bona-fide`, `--n-fraud`,
`--seed` to regenerate data and retrain.
