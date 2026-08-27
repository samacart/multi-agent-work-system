FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependency layer first so app edits do not reinstall the world.
# Dev extras are included on purpose: this is a local-first system, and
# `docker compose run --rm api ./entrypoint.sh test` should just work.
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip && pip install ".[dev]"

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY tests ./tests
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x entrypoint.sh && pip install --no-deps -e .

# Non-root: nothing in this image needs to write to the filesystem.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["./entrypoint.sh", "api"]
