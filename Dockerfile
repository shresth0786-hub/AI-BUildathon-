# =============================================================
# Sentinel AI — single-container Dockerfile
# Multi-stage build: build the React dashboard, then run
# FastAPI + uvicorn serving both the API and the built SPA.
# =============================================================

# -------- stage 1: build frontend --------
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/app/package.json frontend/app/package-lock.json ./
RUN npm ci
COPY frontend/app/ ./
RUN npm run build


# -------- stage 2: backend + runtime --------
FROM python:3.13-slim

WORKDIR /app

# Install Python dependencies first (layer cache)
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy built frontend from stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/app/dist

# Copy database schema files (so app.database can initialise on first run)
# backend/database/db/ is empty at build time; created at container start.
RUN mkdir -p backend/database/db

# Train model artifacts inside the image
WORKDIR /app/backend
RUN python train.py --n-bona-fide 6000 --n-fraud 900 --seed 42

# Expose the API + SPA port
EXPOSE 8100

# Run uvicorn as the container entrypoint
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
