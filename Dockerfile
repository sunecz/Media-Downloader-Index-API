FROM python:3.15.2-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /bin/uv

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Dependencies first, cached until the lock changes
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY app ./app

CMD ["granian", "--interface", "asgi", "--respawn-failed-workers", "--host", "0.0.0.0", "--port", "8000", "app/main:app"]
