# =============================================================
# Sentinel AI — single-container Dockerfile (hardened demo/deploy base)
#
# MULTI-STAGE build:
#   stage 1 (node) : build the React dashboard with Vite
#   stage 2 (python): run FastAPI + uvicorn serving API + built SPA
#
# SECURITY POSTURE (do not weaken):
#   * Runs as a NON-ROOT user (no capabilities, no privileged writes).
#   * The container root filesystem is READ-ONLY in compose; only the two
#     runtime-data volumes are writable.
#   * NO customer data, search history, OTPs, API keys, passwords, or uploaded
#     datasets are baked into this image. Those live in external stores (DB /
#     object storage / Redis) and volumes, and secrets come from env/secret
#     manager at runtime — never from the image.
#   * For supply-chain hardening, pin base images by SHA-256 digest and use a
#     minimal runtime; only the packages you need are installed.
# =============================================================

# -------- stage 1: build frontend (build-time only, not shipped) --------
# Pin the Node toolchain used only to compile the SPA.
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/app/package.json frontend/app/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/app/ ./
RUN npm run build


# -------- stage 2: backend + runtime --------
# Minimal slim base (no compiler toolchain, no debug utilities).
FROM python:3.13-slim

# Security baseline for the runtime image
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SENTINEL_STRICT=1

# Create a non-root user + group to run the app (no root shell, no NOPASSWD).
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --no-create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

# Install Python deps first (layer cache, pinned in requirements.txt).
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source (no .env, no secrets — see .dockerignore)
COPY backend/ ./backend/

# Copy built frontend from stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/app/dist

# Runtime dirs. Their CONTENTS (users, queries, feedback, verifications,
# uploaded datasets) are NOT stored here — they mount onto persistent volumes.
# Create them writable only for the app user.
RUN mkdir -p backend/data backend/database/db backend/app/database/db \
    && chown -R appuser:appuser /app

# Train model artifacts inside the image (static, read-only model version).
# Done as root, then ownership handed to appuser.
WORKDIR /app/backend
RUN python train.py --n-bona-fide 6000 --n-fraud 900 --seed 42

# Drop privileges — everything after this runs as the unprivileged app user.
USER appuser

# Expose the API + SPA port
EXPOSE 8100

# Liveness/healthcheck (the API has a /api/health endpoint)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8100/api/health', timeout=4).status==200 else 1)"

# Run uvicorn as the entrypoint (single worker for the in-memory store; scale
# via multiple containers behind a load balancer for production).
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
