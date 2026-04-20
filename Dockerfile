FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install both backend and ML dependencies
COPY launch_model/requirements.txt ./launch_reqs.txt
COPY backend/requirements.txt ./backend_reqs.txt

RUN pip install --no-cache-dir -r launch_reqs.txt \
    && pip install --no-cache-dir -r backend_reqs.txt

# Create necessary directories
RUN mkdir -p /app/backend/data/models/launch

# Copy application files
# Environment variables are provided by Render at runtime, so do not copy a local .env.
COPY backend/ /app/backend/
COPY launch_model/models/ /app/data/models/launch/

EXPOSE 8000

# Multi-worker ASGI: scale WEB_CONCURRENCY; each worker is a process with its own pools.
ENV WEB_CONCURRENCY=4
ENV THREAD_POOL_MAX_WORKERS=128
CMD gunicorn backend.main:app \
    -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --workers ${WEB_CONCURRENCY} \
    --timeout 120 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --worker-tmp-dir /dev/shm
