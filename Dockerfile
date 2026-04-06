# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* README.md ./
COPY src/ ./src/

# Install dependencies into /app/.venv
RUN uv sync --frozen --no-dev --no-editable

# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS final

WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy source
COPY src/ ./src/

# Make venv the active Python
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# OTLP receiver ports
EXPOSE 4317 4318

# Non-root user
RUN adduser --disabled-password --gecos "" octantis
USER octantis

ENTRYPOINT ["octantis"]
