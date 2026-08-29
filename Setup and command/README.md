# Razorpay Fraud Guardian — How to run it

This folder contains everything you need to set up and run the full-stack
**Razorpay Fraud Guardian** on a Windows machine (backend + frontend).
The actual project lives one level up (`..`); the scripts in this folder are
**self-locating**, so you can run them from anywhere as long as this folder is
inside the project.

---

## What you need installed

| Tool | Version | Check with |
|------|---------|------------|
| Python | 3.10+ (tested on 3.13.5) | `python --version` |
| Node.js | 18+ (tested on 22.17) | `node --version` |
| npm | comes with Node | `npm --version` |
| Git (optional) | any | `git --version` |

> NOTE: the scripts below use the full path `C:\Python313\python.exe`. If your
> Python is elsewhere, edit the `$python` variable at the top of
> `setup.ps1` / `run.ps1` (or make sure `python` is on your PATH).

---

## 1) First-time setup (one time)

Open PowerShell **as Administrator** (needed to create the Python venv), then run:

```powershell
powershell -ExecutionPolicy Bypass -File RUNME\setup.ps1
```

`setup.ps1` will:
1. Create a `.venv` virtual environment in `backend\`.
2. `pip install -r backend\requirements.txt`.
3. Run `python train.py` to generate synthetic Razorpay-style data + train all
   models and save the artifacts (`backend\artifacts\`).
4. `npm install` inside `frontend\app`.
5. Copy `.env.example` → `.env` for backend and frontend (if missing).

Set-up is **optional-only for Twilio / live Razorpay keys**. Without any keys the
system runs fully offline in demo mode (phone-call confirmation is simulated, and
no real Razorpay order is created). You can finish setup now and load keys later.

---

## 2) Run the whole thing (backend + frontend)

```powershell
powershell -ExecutionPolicy Bypass -File RUNME\run.ps1
```

This launches two servers (in hidden windows):

| Service | URL |
|---------|-----|
| FastAPI backend | http://127.0.0.1:8100 |
| React dashboard | http://localhost:5173 |

Press **Enter** in the terminal to stop both servers.

> The Vite frontend proxies `/api` → `:8100`, so everything is served from
> `http://localhost:5173`.

---

## 3) Using the dashboard

Browser → **http://localhost:5173**

The dashboard has panels for:
- **Overview / decisions** — approve / review / block breakdown, cost savings.
- **Live events** — every scored payment with its fraud score, vector & decision.
- **Investigate** — the AI Investigator's ensemble + evidence for a payment.
- **Phone / borderline** — payment-confirmation "call the customer" flow.
- **Learning** — feedback log + re-train with confirmed labels (continual learning).
- **RAG / Admin Q&A** — ask *"what's the issue & what to do about it?"*; the agent
  answers from a runbook **plus the live dataset** (real users, events, feedback).

---

## 4) Manual backend start (instead of run.ps1)

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8100 --reload
```

## 5) Manual frontend start

```powershell
cd frontend\app
npm install
npm run dev
```

---

## 6) Retrain / regenerate data (optional)

```powershell
cd backend
.\.venv\Scripts\python.exe train.py [--n-bona-fide 6000] [--n-fraud 900] [--seed 42]
```

Different `--seed` / counts regenerate the dataset and retrain. The same defaults
are used by the dashboard retrain endpoint (`/api/learning/retrain`).

---

## 7) Optional real integrations (skip for a fully-offline demo)

Copy `backend\.env.example` → `backend\.env` (setup.ps1 already does this) and
fill in keys. `.env` is gitignored — never commit it.

- **Razorpay keys** (`rzp_test_*`) → enable `/api/rzp/create-order` and the real
  `/api/rzp/webhook` ingestion.
- **Twilio keys** (account SID, auth token, phone number) → enable REAL outbound
  phone-call payment confirmation. Twilio's free trial blocks outbound calls until
  billing is added; with no keys the flow runs in simulated mode.

---

## 8) Useful API endpoints

| Method | Path | What it does |
|--------|------|--------------|
| POST | `/api/investigate` | Score a live payment (approve / review / block + evidence) |
| GET | `/api/events?risk=` | Recent payments with scores & decisions |
| GET | `/api/test-metrics` | Honest held-out precision / recall / F1 + cost |
| POST | `/api/feedback/{id}/correct` | Manually mark clean / fraud (continual learning) |
| POST | `/api/learning/retrain` | Retrain on confirmed feedback |
| GET | `/api/users` | Live-investigated users stored in the database |
| POST | `/api/rag/ask` | Admin Q&A (runbook + live dataset) |
| GET | `/api/rag/status` | RAG engine + pipeline source counts |

Full reference: `../README.md#api-endpoints`.

---

## Troubleshooting

- **Port 8100 / 5173 already in use** → stop other Django/Node processes, or change
  the port in `run.ps1` (`--port 8100`, Vite config).
- **`python` not found** → edit the `$python` line in the scripts to your Python
  path, e.g. `$python = "python"` if it's on PATH.
- **No models / empty dashboard** → you skipped `setup.ps1`'s train step; run
  `.\.venv\Scripts\python.exe train.py` in `backend\`.
- **Twilio calls don't sound** → trial blocks outbound; the dashboard shows the
  OTP + call script in simulated mode instead.
