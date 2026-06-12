# syntax=docker/dockerfile:1.7
# ────────────────────────────────────────────────────────────
#  boilerplate-ecom-telebot · production Docker image
#  Phase 5 hardening: multi-stage, non-root, healthcheck, pinned
# ────────────────────────────────────────────────────────────

# ── Stage 1: Build ──────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy

# uv (modern Python package manager)
COPY --from=ghcr.io/astral-sh/uv:0.5.0 /uv /uvx /usr/local/bin/

WORKDIR /build

# ── Install dependencies into a venv ──────────────────────
COPY pyproject.toml ./
RUN uv venv /build/.venv --python=3.12 && \
    uv pip install --python=/build/.venv/bin/python -e "." && \
    # Optional: install sentry-sdk in the builder stage
    uv pip install --python=/build/.venv/bin/python sentry-sdk>=2.0,<3 2>/dev/null || true

# ── Stage 2: Runtime ──────────────────────────────────────
FROM python:3.12-slim AS runtime

# Runtime-only env vars
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"

# ── Create non-root user ─────────────────────────────────
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

# ── Copy venv from builder ───────────────────────────────
COPY --from=builder /build/.venv /app/.venv

# ── Copy application code ─────────────────────────────────
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
COPY locales ./locales
COPY scripts ./scripts

# ── Create data directory for SQLite fallback ────────────
RUN mkdir -p /app/data && chown -R appuser:appuser /app

# ── Healthcheck: verify the bot can start (import check) ──
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python scripts/healthcheck.py || exit 1

# ── Run as non-root ──────────────────────────────────────
USER appuser

# ── Default command: polling mode ────────────────────────
CMD ["python", "-m", "bot_app.main"]
