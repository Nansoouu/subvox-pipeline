# ── Dockerfile — SUBVOX Pipeline (API + Celery Worker) ───────────
FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY backend/migrations/ ./migrations/

ENV PYTHONPATH=/app/backend

RUN addgroup --system --gid 1001 subvox && \
    adduser --system --uid 1001 --gid 1001 subvox && \
    mkdir -p /tmp/subvox-processing /app/storage && \
    chown -R subvox:subvox /tmp/subvox-processing /app/storage

USER subvox

# ── API (par défaut) ────────────────────────────────────────────
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# ── Celery Worker ───────────────────────────────────────────────
FROM base AS worker
USER subvox
WORKDIR /app

ENV C_FORCE_ROOT=no

CMD ["celery", "-A", "core.celery_app", "worker", "--loglevel=info", "--concurrency=2", "-Q", "video_processing,video_analysis"]
