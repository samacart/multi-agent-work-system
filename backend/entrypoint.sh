#!/usr/bin/env sh
# Container entrypoint. `api` runs migrations then serves; `worker` waits for the
# schema (the api applies it) then consumes jobs.
set -e

ROLE="${1:-api}"

case "$ROLE" in
  api)
    echo "[entrypoint] applying database migrations"
    alembic upgrade head
    echo "[entrypoint] starting API on :8000"
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    echo "[entrypoint] starting worker"
    exec python -m app.worker.main
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  test)
    exec python -m pytest -q
    ;;
  *)
    exec "$@"
    ;;
esac
