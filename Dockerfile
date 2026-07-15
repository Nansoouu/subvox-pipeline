# ── Dockerfile — SUBVOX Pipeline (API + Celery Worker) ───────────
FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    build-essential \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install deno for yt-dlp YouTube extraction
RUN curl -fsSL https://deno.land/install.sh | sh -s -- -y && \
    cp /root/.deno/bin/deno /usr/local/bin/deno && \
    chmod 755 /usr/local/bin/deno

RUN addgroup --system --gid 1001 subvox && \
    adduser --system --uid 1001 --gid 1001 subvox

WORKDIR /app

COPY --chown=subvox:subvox requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=subvox:subvox backend/ ./backend/
COPY --chown=subvox:subvox backend/migrations/ ./migrations/

ENV PYTHONPATH=/app/backend

RUN mkdir -p /tmp/subvox-processing /app/storage && \
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

CMD ["celery", "-A", "core.celery_app", "worker", "--loglevel=info", "--concurrency=4", "-Q", "video_processing,video_analysis,short,medium,long,xlong,economy"]
