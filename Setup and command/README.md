# Razorpay Fraud Guardian — How to run it

This folder contains everything you need to set up and run the full-stack
**Sentinel AI — Razorpay Fraud Guardian** on a Windows machine (backend +
frontend). The actual project lives one level up (`..`); the scripts in this
folder are **self-locating**, so you can run them from anywhere as long as this
folder is inside the project.

---

## What you need installed

### Option A — local run (recommended for development)

| Tool | Version | Check with |
|------|---------|------------|
| Python | 3.10+ (tested on 3.13.5) | `python --version` |
| Node.js | 18+ (tested on 22.17) | `node --version` |
| npm | comes with Node | `npm --version` |
| Git (optional) | any | `git --version` |

### Option B — Docker

| Tool | Version | Check with |
|------|---------|------------|
| Docker | 20.10+ | `docker --version` |

No local Python or Node installation required.

> NOTE: the scripts below use the full path `C:\Python313\python.exe`. If your
> Python is elsewhere, edit the `$python` variable at the top of
> `setup.ps1` / `run.ps1` (or make sure `python` is on your PATH).

---

## 1) First-time setup (one time — local run)

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
5. Copy `.env.example` -> `.env` for backend and frontend (if missing).

Set-up is **optional-only for Twilio / live Razorpay keys**. Without any keys the
system runs fully offline in demo mode (OTP confirmation is simulated, and no
real Razorpay order is created). You can finish setup now and load keys later.

---

## 2) Run the whole thing (backend + frontend — local)

```powershell
powershell -ExecutionPolicy Bypass -File RUNME\run.ps1
```

This launches two servers (in hidden windows):

| Service | URL |
|---------|-----|
| FastAPI backend | http://127.0.0.1:8100 |
| React dashboard | http://localhost:5173 |

Press **Enter** in the terminal to stop both servers.

> The Vite frontend proxies `/api` -> `:8100`, so everything is served from
> `http://localhost:5173`.

---

## 3) Docker (single container)

Build and run in one step — no local Node or Python setup needed:

```bash
docker build -t sentinel-ai .
docker run -p 8100:8100 sentinel-ai
```

Open **http://localhost:8100** — the built React dashboard and the FastAPI API
are both served from the same container.

> The first build takes a few minutes (installs deps, builds frontend with Vite,
> trains the model). Subsequent builds are fast thanks to layer caching.

---

## 4) Using the dashboard

Browser -> **http://localhost:5173** (local) or **http://localhost:8100** (Docker)

The dashboard has panels for:
- **Overview / decisions** — approve / review / block breakdown, cost savings.
- **Live events** — every scored payment with its fraud score, vector & decision.
- **Investigate** — the AI Investigator's ensemble + evidence for a payment.
- **Phone / OTP** — payment-confirmation flow via **phone call, SMS, or
  WhatsApp** (simulated when no Twilio keys present).
- **Learning** — feedback log + re-train with confirmed labels (continual
  learning).
- **SENbot** — ask *"what's the issue & what to do about it?"*; the assistant
  answers from a runbook **plus the live dataset** (real users, events, feedback).
  Admin can also search and delete users for data hygiene.
- **Users** — live-investigated users with search and deletion (admin only).

### Login

| Role | Username | Password |
|------|----------|----------|
| Admin | `admin` | `admin123` |

The admin has full access: live scoring, investigation reports, OTP
verification, SENbot Q&A, and continual learning retrain.

---

## 5) Manual backend start (instead of run.ps1)

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8100 --reload
```

## 6) Manual frontend start

```powershell
cd frontend\app
npm install
npm run dev
```

---

## 7) Retrain / regenerate data (optional)

```powershell
cd backend
.\.venv\Scripts\python.exe train.py [--n-bona-fide 6000] [--n-fraud 900] [--seed 42]
```

Different `--seed` / counts regenerate the dataset and retrain. The same defaults
are used by the dashboard retrain endpoint (`/api/learning/retrain`).

---

## 8) Optional real integrations (skip for a fully-offline demo)

Copy `backend\.env.example` -> `backend\.env` (setup.ps1 already does this) and
fill in keys. `.env` is gitignored — never commit it.

- **Razorpay keys** (`rzp_test_*`) -> enable `/api/rzp/create-order` and the real
  `/api/rzp/webhook` ingestion.
- **Twilio keys** (account SID, auth token, phone number) -> enable real outbound
  phone / SMS / WhatsApp payment confirmation. Twilio's free trial blocks
  outbound calls until billing is added; with no keys the flow runs in simulated
  mode and all OTP details are shown in the dashboard.

---

## 9) Useful API endpoints

| Method | Path | What it does |
|--------|------|--------------|
| POST | `/api/auth/login` | Authenticate; returns JWT + role |
| GET | `/api/summary` | Model summary + decision metrics |
| GET | `/api/events?risk=&limit=` | Recent payments with scores & decisions |
| GET | `/api/events/{event_id}` | Full investigation report for one event |
| POST | `/api/investigate` | Score a live payment (approve / review / block + evidence) |
| GET | `/api/test-metrics` | Honest held-out precision / recall / F1 + cost |
| POST | `/api/feedback/{id}/correct` | Manually mark clean / fraud (continual learning) |
| POST | `/api/learning/retrain` | Retrain on confirmed feedback |
| GET | `/api/users` | Live-investigated users stored in the database |
| GET | `/api/users/search?q=` | Search users by phone / ID / name / merchant |
| DELETE | `/api/users/{user_id}` | Delete user + their events (admin only) |
| POST | `/api/rag/ask` | SENbot Q&A (runbook + live dataset) |
| GET | `/api/rag/status` | SENbot + pipeline source counts |
| POST | `/api/verification/{event_id}` | Start phone / SMS / WhatsApp OTP verification |
| POST | `/api/verification/{event_id}/public` | OTP verification for the review band demo |

---

## Troubleshooting

- **Port 8100 / 5173 already in use** -> stop other Django/Node processes, or
  change the port in `run.ps1` (`--port 8100`, Vite config).
- **`python` not found** -> edit the `$python` line in the scripts to your Python
  path, e.g. `$python = "python"` if it's on PATH.
- **No models / empty dashboard** -> you skipped `setup.ps1`'s train step; run
  `.\.venv\Scripts\python.exe train.py` in `backend\`.
- **Twilio calls don't sound** -> trial blocks outbound; the dashboard shows the
  OTP + call script in simulated mode instead.
- **Docker build fails** -> ensure Docker is running and you have enough disk
  space (the image is ~500 MB including trained model artifacts).
