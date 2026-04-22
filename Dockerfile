# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH"

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python /app/scripts/healthcheck.py || exit 1

CMD ["sh", "-c", "alembic upgrade head && exec python -m src.main"]
