# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy

# uv (modern Python package manager)
COPY --from=ghcr.io/astral-sh/uv:0.5.0 /uv /uvx /usr/local/bin/

WORKDIR /app

# ── deps first (cache-friendly) ────────────────────────────────
COPY pyproject.toml ./
RUN uv venv /app/.venv --python=3.12 && \
    uv pip install --python=/app/.venv/bin/python -e "."

# ── code ───────────────────────────────────────────────────────
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
COPY locales ./locales
COPY scripts ./scripts

RUN mkdir -p /app/data && chown -R 1000:1000 /app

USER 1000
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/src

CMD ["python", "-m", "bot_app.main"]
