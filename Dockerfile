# syntax=docker/dockerfile:1.7
# Multi-arch image for Gmail Attachments MCP
# Builds for linux/arm64 (Orange Pi) and linux/amd64 (macOS testing, x86 servers).

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Tesseract for image OCR (with Slovak + English language packs)
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-slk \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies layer (cached separately from source)
COPY requirements.txt .
RUN pip install -r requirements.txt

# App source
COPY app/ ./app/

# Runtime user (don't run as root)
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin mcp && \
    mkdir -p /data && chown -R mcp:mcp /data /app

USER mcp

ENV DATA_DIR=/data \
    HOST=0.0.0.0 \
    PORT=8765

VOLUME ["/data"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8765/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765", "--proxy-headers"]
