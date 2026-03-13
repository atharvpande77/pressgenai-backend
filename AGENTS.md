# Repository Guidelines

## Purpose & Scope
- Backend work lives entirely under `src/`. `src/app.py` wires FastAPI, mounts the routers, and exposes `/` plus `/api/*` under `root_path /pressgenai`.
- Migrations are in `alembic/` (history under `alembic/versions/`).
- Treat `/frontend`, `/news-agg-html`, `.venv/`, `.tmp/`, and any directory listed in `.gitignore` as out of scope for this guide.

## Architecture & Layout
- Each domain under `src/` (e.g., `admin`, `auth`, `stories`, `editor`, `creators`, `media`, `news`, `insurance`, `common`) follows a router → service → schemas split.
- Shared pieces live in `src/config/` (settings, database, OpenAI client) plus `src/models.py`/`src/schemas.py` for cross-domain models.
- Settings use `pydantic-settings` to load `.env`; the database helper exposes `get_session()` and a `Session` dependency.
- Business rules stay in the service layer; routers should remain lightweight.
- Routes for stories, editor, creator, auth, admin, news, media, and common are exposed in the schema (`insurance` is not).

## Environment & Setup
- Target runtime: Python 3.12.8. Create and activate a virtual environment before installing dependencies with `pip install -r requirements.txt`.
- `.env` holds secrets and is ignored by git; never commit credentials. Keep it synced with `src/config/settings.py`.
- Required variables include `POSTGRES_CNX_STR_LOCAL`, `DEV_DB_CNX_STR`, `ENV`, OpenAI/Serp/WATI keys, AWS credentials, bucket names, assistant IDs, JWT secrets, and any other value referenced in `src/config/settings.py`.

## Common Commands
- `python -m venv .venv && . .venv/Scripts/activate` (Windows) or `source .venv/bin/activate` (Unix) + `pip install -r requirements.txt`.
- `uvicorn src.app:app --reload --host 0.0.0.0 --port 8000` — run the API locally.
- `alembic upgrade head` after schema changes.
- `alembic revision --autogenerate -m "description"` to capture migrations.

## Development Practices
- Keep routers focused on wiring dependencies, schemas, and responses. Push business logic (queries, validations, updates) into `service.py`.
- Use the `src/config/database.Session` dependency and `AsyncSession` helpers for DB work. Always `commit()` or `rollback()` explicitly as needed.
- When data models change, update `src/models.py`, add a migration, and adjust any related tests.
- Prefer `rg` for searching and `apply_patch` for single-file edits.
- Before committing, exercise affected endpoints locally with `uvicorn` + curl/Postman and run `alembic upgrade head` to ensure migrations apply cleanly.

## Security & Configuration Notes
- Secrets belong in `.env` only. Do not hardcode API keys, tokens, or credentials in the repo.
- CORS is currently permissive; be mindful when adding new routes or integrating third-party origins.
- Any change touching IAM credentials, OpenAI assistants, or payment/chatbot flows must include notes on where those values live and how to rotate them.

## Gitignore & Off-Limits Paths
- Follow `.gitignore`: keep `.venv/`, `.vercel/`, `.tmp/`, `/frontend/`, `/news-agg-html/`, `/src/insurance/scripts/`, `.vscode/`, `__pycache__/`, and compiled artifacts (`*.pyc`) out of commits.
- Don’t commit generated files or credentials. Check `git status` often and stage only relevant files.

## Helpful Reminders
- The stack is FastAPI + async SQLAlchemy/Asyncpg with Redis/Postgres. Keep async usage lean and avoid blocking operations.
- Consult `src/app.py` to understand middleware, tags, and router prefixes.
- When adding config keys, update `src/config/settings.py` and the documentation (README/AGENTS.md) so future contributors know what to provide.
