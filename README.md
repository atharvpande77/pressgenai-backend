# rss-feed

Backend service for RSS/news processing and content workflows, built with FastAPI and Alembic.

## Scope
This README covers only backend code in `src/` and migrations in `alembic/`.
`/frontend` and `/news-agg-html` are intentionally out of scope.

## Prerequisites
- Python `3.12.8`
- PostgreSQL (configured through `.env`)

## Local Setup
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Run the API
```powershell
uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
```

## Database Migrations
```powershell
alembic upgrade head
alembic revision --autogenerate -m "add_new_field"
```

## Code Organization
- `src/app.py`: FastAPI app and router registration
- `src/<module>/router.py`: endpoints
- `src/<module>/service.py`: business logic
- `src/<module>/schemas.py`: request/response models
- `src/config/`: settings and DB configuration
- `alembic/versions/`: migration history

## Contribution Notes
- Use clear, descriptive commit messages.
- Keep route handlers thin; place logic in services.
- Add/adjust tests for changed behavior where applicable.
