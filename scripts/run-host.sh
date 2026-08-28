#!/usr/bin/env bash
# Run the backend on the host, with Postgres and Redis still in Docker.
#
# This is the mode to use with AGENT_RUNTIME=claude_code. Claude Code is a CLI
# with filesystem and shell access; it authenticates with your existing login,
# needs no API key, and cannot usefully run inside the API container - it has to
# see the repository you are asking it to work on.
#
#   ./scripts/run-host.sh            # api + worker on the host
#   ./scripts/run-host.sh api        # api only
#   ./scripts/run-host.sh worker     # worker only
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ROLE="${1:-all}"
VENV="$ROOT/backend/.venv"

[ -d "$VENV" ] || {
  echo "No virtualenv at $VENV. Create it with:"
  echo "  cd backend && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e '.[dev]'"
  exit 1
}

# Host mode talks to the containers over published ports, not compose DNS.
export DATABASE_URL="${HOST_DATABASE_URL:-postgresql+asyncpg://postgres:postgres@localhost:${POSTGRES_PORT:-5432}/agent_work}"
export REDIS_URL="${HOST_REDIS_URL:-redis://localhost:${REDIS_PORT:-6379}/0}"

# Load .env without clobbering the two above.
if [ -f .env ]; then
  while IFS='=' read -r key value; do
    case "$key" in
      ''|\#*|DATABASE_URL|REDIS_URL) continue ;;
    esac
    export "$key=$value"
  done < <(grep -vE '^\s*(#|$)' .env)
fi

# On the host, local paths are real paths - not the container's /data/sources.
export ALLOWED_SOURCE_ROOTS="${HOST_ALLOWED_SOURCE_ROOTS:-$ROOT/data/sources}"

echo "[run-host] database : $(echo "$DATABASE_URL" | sed 's|://[^@]*@|://***@|')"
echo "[run-host] runtime  : ${AGENT_RUNTIME:-mock}"
echo "[run-host] embedder : ${EMBEDDING_PROVIDER:-hash}"
echo "[run-host] roots    : $ALLOWED_SOURCE_ROOTS"

if [ "${AGENT_RUNTIME:-}" = "claude_code" ]; then
  command -v "${CLAUDE_CODE_BINARY:-claude}" >/dev/null 2>&1 || {
    echo "[run-host] AGENT_RUNTIME=claude_code but '${CLAUDE_CODE_BINARY:-claude}' is not on PATH." >&2
    exit 1
  }
  echo "[run-host] claude   : $(command -v "${CLAUDE_CODE_BINARY:-claude}")"
fi

echo "[run-host] starting postgres and redis"
docker compose up -d postgres redis >/dev/null
for _ in $(seq 1 60); do
  docker compose exec -T postgres pg_isready -U postgres -d agent_work >/dev/null 2>&1 && break
  sleep 1
done

echo "[run-host] applying migrations"
(cd backend && "$VENV/bin/alembic" upgrade head >/dev/null)

start_api()    { (cd backend && exec "$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port "${API_PORT:-8000}"); }
start_worker() { (cd backend && exec "$VENV/bin/python" -m app.worker.main); }

case "$ROLE" in
  api)    start_api ;;
  worker) start_worker ;;
  all)
    start_worker & WORKER_PID=$!
    trap 'kill $WORKER_PID 2>/dev/null || true' EXIT INT TERM
    start_api
    ;;
  *) echo "usage: $0 [api|worker|all]" >&2; exit 2 ;;
esac
