# Repository Guidelines

## Purpose & Scope
- Backend-only work lives in `src/`; `src/app.py` wires FastAPI, mounts all routers, and exposes `/` plus `/api/*` under `root_path` `/pressgenai`.
- Migrations live in `alembic/` with the history under `alembic/versions/`; `/frontend`, `/news-agg-html`, `.venv/`, `.tmp/`, and any directories listed in `.gitignore` are intentionally out of scope for this guide.

## Architecture & Layout
- Each domain under `src/` (e.g., `admin`, `auth`, `stories`, `editor`, `creators`, `media`, `news`, `insurance`, `common`) follows the router/service/schemas split: `router.py` defines endpoints, `service.py` holds business logic, and `schemas.py` defines typed request/response models.
- Shared pieces live in `src/config/` (settings, DB, OpenAI client) plus `src/models.py`/`src/schemas.py` for cross-domain models/DTOs.
- `src/config/settings.py` is a `pydantic-settings` config that loads `.env`; `src/config/database.py` instantiates the async SQLAlchemy engine/session based on `ENV`, `DEV_DB_CNX_STR`, or `POSTGRES_CNX_STR_LOCAL`.
- The app applies permissive CORS for now and mounts routers for stories, editor, creator, auth, admin, news, media, common, and insurance. Keep business rules in the service layer and keep routers thin.

## Environment & Setup
- Python 3.12.8 is the target runtime. Setup a venv, activate it, and install dependencies with `pip install -r requirements.txt` before coding.
- `.env` holds secrets and is ignored by git; do not commit credentials. Required variables include (but are not limited to) `POSTGRES_CNX_STR_LOCAL`, `DEV_DB_CNX_STR`, `ENV`, `SERP_API_KEY`, `EXHAUSTED_SERP_API_KEY1`, `OPENAI_API_KEY`, `JWT_SECRET`, `JWT_REFRESH_SECRET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `PROFILE_IMAGE_S3_BUCKET`, assistant IDs (`RETIREMENT_*`, `TERM_*`, `CHILD_EDUCATION_*`, `TAX_PLANNING_*`), and WATI tokens. Keep the list in sync with `src/config/settings.py`.

## Common Commands
- `python -m venv .venv` && activate + `pip install -r requirements.txt`: bootstrap dependencies.
- `uvicorn src.app:app --reload --host 0.0.0.0 --port 8000`: run the API in dev mode.
- `alembic upgrade head`: bring the database schema up to date.
- `alembic revision --autogenerate -m "describe change"`: add migrations after model changes.

## Development Practices
- Prefer URLs/logic in `service.py`, keep routers only for wiring dependencies/schemas. Use dependency injection via `src/config/database.Session` and `get_session()` helpers.
- When modeling data, update `src/models.py` and add an Alembic migration for any schema change. Referencing enums in models (e.g., `UserStoryStatus`, `UserStoryPublishStatus`, `NewsCategory`) should match server-side logic and should be reused in other modules.
- Add or adjust tests near the feature (`src/<module>/test_*.py`) if the behavior warrants it; automated coverage is limited, so every new feature should come with at least minimal verification.
- Before committing, run the impacted endpoint manually (local `uvicorn` + curl/postman) and ensure `alembic upgrade head` runs cleanly against your dev DB.
- Commit messages should be descriptive and imperative (e.g., `news: handle duplicate feed items`), and PRs should summarize behavior changes, link relevant tasks, document migration IDs/rollback impact, and include API examples when endpoints change.

## Security & Configuration Notes
- Keep secrets in `.env` only; never hardcode tokens/keys in the repo. `.env` is listed in `.gitignore`, so copy the file from secure sources when needed.
- Review CORS settings, database URLs, and AWS/OpenAI configuration in `src/config/` before promoting any change.
- Changes touching IAM credentials, OpenAI assistants, or payment/chatbot flows should include notes about where those values live and how to rotate them safely.

## Gitignore & Off-Limits Paths
- Follow `.gitignore` strictly: ignore `.venv/`, `.vercel/`, `.tmp/`, `/frontend/`, `/news-agg-html/`, `/src/insurance/scripts/`, `.vscode/`, `__pycache__/`, and compiled artifacts (`*.pyc`, etc.).
- Do not commit generated files or credentials; prefer checking `git status` often to ensure excluded directories stay out of commits.

## Helpful Reminders
- FastAPI + SQLAlchemy/Asyncpg is the stack; keep async/await lean.
- When in doubt, look at `src/app.py` and the routers to understand how middleware, tagging, and prefixing behave.
- If you add new config, update both `src/config/settings.py` and the README/AGENTS so future contributors know what to provide.
