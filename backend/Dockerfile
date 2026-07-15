# syntax=docker/dockerfile:1
# Runtime image for the FastAPI API, worker, and scheduler.

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/backend:/app/harvester:/app/ai \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

RUN mkdir -p /app/.cache/huggingface

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./

# Install heavyweight third-party dependencies before application source. The
# empty package roots let setuptools read pyproject metadata without coupling
# this layer to frequently changing Python files.
RUN --mount=type=cache,target=/root/.cache/pip \
    mkdir -p backend harvester ai \
    && python -m pip install --upgrade pip \
    && python -m pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch>=2.1" \
    && python -m pip install ".[ai,test]" \
    && rm -rf backend harvester ai

# Source-only edits invalidate only this inexpensive editable-project layer.
COPY backend ./backend
COPY harvester ./harvester
COPY ai ./ai
COPY scripts ./scripts

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --no-deps -e .

EXPOSE 8111
