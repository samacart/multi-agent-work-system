# Backend

FastAPI + SQLAlchemy (async) + Alembic. See the repository README for the full quickstart.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest -q      # offline: SQLite, mock runtime, no API keys
```
