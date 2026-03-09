# Repository Guidelines

## Project Structure & Module Organization
Backend code lives in `src/` as a FastAPI app, with feature modules organized by domain (`auth`, `stories`, `news`, `admin`, `editor`, `creators`, `insurance`, etc.). Most domains follow `router.py`, `service.py`, and `schemas.py`.
`src/app.py` is the API entrypoint and mounts all routers.
Database migrations are in `alembic/` and `alembic/versions/`.
This guide intentionally ignores `/frontend` and `/news-agg-html`.

## Build, Test, and Development Commands
- `python -m venv .venv; .\.venv\Scripts\activate; pip install -r requirements.txt`: set up backend dependencies.
- `uvicorn src.app:app --reload --host 0.0.0.0 --port 8000`: run backend locally.
- `alembic upgrade head`: apply all DB migrations.
- `alembic revision --autogenerate -m "add_x"`: generate a migration after model changes.

## Coding Style & Naming Conventions
Use 4-space indentation in Python and keep naming in `snake_case` for modules/functions/variables. Prefer explicit type-aware schemas and keep route handlers thin by placing logic in `service.py`.
Name Alembic revisions with clear intent (avoid placeholder names).

## Testing Guidelines
Automated backend test coverage is currently limited; add tests with each feature or bugfix.
Place new tests near the feature (for example, `src/<module>/test_*.py`) or under a dedicated `tests/` package if introduced.
Minimum check before commit: run impacted endpoints locally and ensure migrations apply cleanly with `alembic upgrade head`.

## Commit & Pull Request Guidelines
Recent history includes short descriptive commits and timestamp-style commits; prefer descriptive, imperative messages instead (example: `news: handle duplicate feed items`).
PRs should include:
- A clear summary of behavior changes.
- Linked issue/task ID (if available).
- Notes on DB migrations (revision ID and rollback impact).
- API examples for changed endpoints.

## Security & Configuration Tips
Keep secrets in `.env` only; never commit credentials or tokens.
Review CORS, auth, and DB settings in `src/config/` before promoting to production.
