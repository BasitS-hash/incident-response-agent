# syntax=docker/dockerfile:1
# Backend image for the Incident Response Agent API.
# Build from the repo root:  docker build -f backend/Dockerfile -t ir-agent-backend .
FROM python:3.12-slim AS base

# Prevent Python from writing pyc files / buffering stdout.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy application source.
COPY backend ./backend

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/backend/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Basic container healthcheck against the /health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else sys.exit(1)"

CMD ["uvicorn", "backend.api.main:api", "--host", "0.0.0.0", "--port", "8000"]
