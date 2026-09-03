# Sentinel AI — Security & Production Hardening

Sentinel AI is first and foremost a **buildathon demo**. This document explains
how we keep it safe for a demo **and** what to do before it ever runs against
real customers, real money, or a corporate environment. Follow this guidance for
any "company use."

## 1. What the Docker image must NOT contain

The **only** thing baked into the image is the tested application code and the
**approved model version** (trained + validated at build time). Everything below
is **runtime state** and must live **outside** the image:

| Data | Store it in | Example |
|------|-------------|---------|
| Customer / payer data | Database or object storage | Postgres, S3-compatible store |
| Investigated users, queries | Database | `sentinel_db` volume today → DB |
| Search history | Database / search index | Postgres, Redis |
| Feedback / continual-learning labels | Database | Postgres |
| OTPs & verification sessions | Redis (TTL) + audit log in DB | Redis with expiry |
| Uploaded datasets | Object storage | S3 / MinIO (not the image) |
| API keys & passwords | Secret manager | Vault, AWS Secrets Manager, GH secrets |
| JWT signing secret | Secret manager/env | `SENTINEL_AUTH_SECRET` |

> These never go into a `RUN`, `ENV`, `COPY`, or `LABEL` in the Dockerfile, and
> are excluded from the build context by `.dockerignore`.

## 2. Secrets management

Never store secrets in the Dockerfile, `docker-compose.yml`, or git.

- **Auth signing secret** — `SENTINEL_AUTH_SECRET`. In production use a
  randomly generated value (64+ random bytes) injected from a secret manager.
  With `SENTINEL_STRICT=1` (set in the hardened container), the app **refuses to
  start** if the insecure demo default is used.
- **Admin password** — `SENTINEL_ADMIN_PASSWORD`. In production this should
  come from your identity provider / SSO, or a DB-backed user store with hashed
  passwords, not a static demo account.
- **Twilio / Razorpay keys** — `TWILIO_*`, `RAZORPAY_*` from the secret manager.
  The demo runs fully offline (`simulated` mode) with no keys.

## 3. Authentication & authorization

- The demo uses a lightweight HMAC-signed token and a single `admin` role. For
  production, replace with a real auth system (OAuth2/OIDC or your IdP), and:
  - store only **hashed** passwords,
  - enforce short-lived tokens + refresh rotation,
  - add per-user authorization (not just a shared admin),
  - use `require_role()` consistently on every privileged route.

## 4. CORS

- Default `allow_origins=["*"]` is only acceptable for the local demo.
- For production set `SENTINEL_CORS_ORIGINS` to your exact dashboard origin(s),
  e.g. `https://dashboard.yourcompany.com`. `allow_credentials` stays `False`
  unless you genuinely need cookies.

## 5. OTP handling

- OTPs must be delivered to the payer's phone and **never returned** to the API
  response. In production set `SENTINEL_OTP_REDACT_OTP=1` (or it auto-redacts in
  real mode) so the browser/API only ever sees `******`.
- The simulated mode shows the OTP **intentionally** so an analyst can complete
  a demo call — disable it for any non-demo deployment.
- Rate-limit verification attempts and cap wrong-OTP retries server-side
  (already implemented; raise `_MAX_ATTEMPTS` only with extreme care).
- Consider HMAC/encrypting OTPs at rest and never logging them.

## 6. Container hardening (already applied in `Dockerfile` / `docker-compose.yml`)

- **Non-root user** — container runs as `appuser` (uid 10001), no root shell.
- **Read-only root filesystem** — only the two runtime-data volumes are writable.
- **Drop capabilities** — `cap_drop: [ALL]`, `no-new-privileges: true`.
- **Minimal base image** — `python:3.13-slim`, no debug toolchain.
- **Healthcheck** — `/api/health` gates restart/liveness decisions.
- **Supply-chain** — for hardened deployments pin base images by **SHA-256
  digest**, run dependency vulnerability scanning (e.g. `trivy`, `grype`,
  `pip-audit`, `npm audit`), and sign/tag images with provenance metadata.

## 7. Data flow & persistence

- Model artifacts are static and read-only (approved model version).
- All runtime writes go to named volumes today (`sentinel_data`,
  `sentinel_db`). For company use, replace these volumes with a managed DB +
  object storage and move OTP sessions to Redis with a TTL.

## 8. Reporting a vulnerability

For the demo, report issues via the GitHub repository issues.
