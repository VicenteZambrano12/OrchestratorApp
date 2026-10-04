# OrchestratorApp

## Backend structure

T

Empty folders are retained with `.gitkeep` files. Python-generated
`__pycache__` folders are excluded by `.gitignore`.

## Running the backend

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first.
From the repository root:

```bash
uv sync --project backend --locked
uv run --project backend --locked uvicorn app:app --app-dir backend/src --reload
```

Dependencies are declared in `backend/pyproject.toml` and pinned in
`backend/uv.lock`. `uv sync` creates the backend's `.venv` automatically; manual
activation is not required. To add a dependency, run
`uv add --project backend <package>`, and commit both the manifest and lockfile.

The FastAPI application is defined in `backend/src/app.py` and imports the health
router from `backend/src/api/Endpoint/health.py`. Its initial endpoint is `GET /health`,
which returns HTTP 200 with `{"status": "ok"}`. Interactive API documentation is
available at `http://127.0.0.1:8000/docs`.