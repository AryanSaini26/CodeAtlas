# syntax=docker/dockerfile:1
#
# Production image for the hosted Stratum control plane (Fly.io).
# Serves the FastAPI hosted API + the dashboard SPA from one process.
# The root-level Dockerfile remains the CLI/tool image; this one is for deploy.

# --- Stage 1: build the dashboard SPA ---
FROM node:20-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python app ---
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[all]"

COPY --from=frontend /frontend/dist ./frontend/dist

# SQLite metadata + per-repo graphs live on a persistent Fly volume at /data.
ENV PORT=8080
EXPOSE 8080

# `ui` mounts the hosted routes + serves the built SPA. Host 0.0.0.0 so Fly's
# proxy can reach it; port comes from $PORT.
CMD ["sh", "-c", "codeatlas ui --no-browser --host 0.0.0.0 --port ${PORT:-8080} --db /data/graph.db --hosted-db /data/hosted.db --dist /app/frontend/dist"]
