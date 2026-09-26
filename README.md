# Pressgen.ai Backend

A FastAPI-based backend that orchestrates creator/editor workflows, article generation, and newsroom tooling for the Pressgen.ai platform.

## Project Overview (Recruiter Notes)
- **Mission:** Enable creators and editors to publish structured, AI-assisted articles with fine-grained control over cities, categories, and publication workflows.
- **Team Velocity:** Thin routers + dedicated services keep domains (stories, editor, creators, news, media, common) fast to iterate on.
- **Visibility:** `/pressgenai` is the shared root path; public schema exposes all routers except insurance (used for infra/legacy tasks).
- **Signal:** JWT + refresh tokens, rate limiting, async DB access, and AWS-integrated profile images support real-world SaaS demands.

## Problem
Faster journalism requires composable workflows for creators, editors, and admins. The backend centralizes authentication, onboarding, attribution, and article management so the frontend can focus on storytelling without wiring together Redis, Postgres, and OpenAI every time.

## Architecture
- FastAPI app wires routers for `stories`, `editor`, `creator`, `auth`, `admin`, `news`, `media`, and `common`. Each domain follows a router → service → schemas pattern.
- Shared config/live code lives in `src/config/` (`settings`, `database`, AWS/OpenAI clients).
- SQLAlchemy models (`src/models.py`) describe users/authors/cities/categories and drive async queries via `src/config/database`.
- Insurance-related routers run behind the scenes and are excluded from the OpenAPI schema (`include_in_schema=False`).

### Routes included in the schema
- `/api/stories` – Story + generation orchestration.
- `/api/editor` – Editor dashboards, article edits, creator management, profile/password knobs.
- `/api/creator` – Creator registration, onboarding, profile updates, password changes.
- `/api/auth` – JWT issuance with refresh flow.
- `/api/admin` – Super-admin user creation, published article visibility.
- `/api/news` – Published article catalog (newest first) and creator profiles.
  - `GET /api/news/` filters by `category_id`/`city_id` (UUID) or `category`/`city` (slug, e.g. `local-news`, `nagpur`); the total match count is in the `X-Total-Count` header.
  - Each article has ordered `categories` and a `primary_category` (the first; used for the public URL `/{category}/{slug}`). Order is stored in `article_categories.position`.
  - `GET /api/news/sitemap` (slug, primary category, timestamps) and `GET /api/news/authors` (usernames + latest article time) feed the website's sitemaps.
  - Timestamps are stored as naive IST and serialized with an explicit `+05:30` offset.
- `/api/media` – Image uploads + metadata (tagged with `media`/`images`).
- `/api/common` – Shared endpoints (healthchecks, utilities).
- `/api/insurance` is intentionally hidden and not part of the public schema.

## Tech Stack
- Python
- FastAPI
- Redis
- Postgres
- Docker

## Key Features
- JWT authentication with refresh tokens
- Redis rate limiting
- Async APIs powered by FastAPI + async SQLAlchemy
- Real-time chat leveraging Socket.IO (media/news domains)
- Modular router/service/schemas separation for each vertical
- Profile image handling via AWS S3 mixins and computed URLs

## System Design
Client requests hit `/pressgenai/api/<domain>`, FastAPI routes parse/validate via Pydantic schemas, inject dependencies (`Session`, role guards), and forward calls to `service.py`, which encapsulates business rules (DB, AWS uploads, hashing, JWT helpers). Responses reuse shared mixins for profile or image data so every schema consistently exposes `profile_image`, `images`, `categories`, and `cities`. Background-heavy operations rely on Redis/Postgres caching and summary tables (e.g., article categories stored via `ArticleCategories` overlays).

### Architecture Diagrams
```mermaid
graph TD
    Client -->|JWT| FastAPI
    FastAPI --> Router[Routers: stories, creator, editor, news, admin, media, common]
    Router --> Service[Domain Services (business logic)]
    Service --> Database[(Postgres via async SQLAlchemy)]
    Service -->|uploads| AWS_S3[(S3)]
    Service -->|cache| Redis
    Service -->|retries| Queue[Background jobs / queues]
    Database --> Cities
    Database --> Authors
    Database --> GeneratedUserStories
    Database --> Categories
    Router --> Insurance[Insurance router (include_in_schema=False)]
```

## Example API Requests
```bash
curl -H "Authorization: Bearer $JWT_TOKEN" https://api.example.com/pressgenai/api/news/

curl -X POST https://api.example.com/pressgenai/api/creator/onboarding \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
        "date_of_birth":"1990-01-01",
        "highest_education":"bachelors",
        "work_status":"salaried",
        "city_id":"<uuid>",
        "links":[{"link_type":"portfolio","url":"https://portfolio.example.com","platform":"web"}]
      }'
```

## Setup Instructions
1. `python -m venv .venv` && `.\.venv\Scripts\activate` (Windows) or `source .venv/bin/activate`.
2. `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and fill required vars (`ENV`, `POSTGRES_CNX_STR_LOCAL`, `DEV_DB_CNX_STR`, OpenAI/Serp/AWS/JWT secrets, assistant IDs, WATI tokens, etc.).
4. `alembic upgrade head`.
5. `uvicorn src.app:app --reload --host 0.0.0.0 --port 8000`.
6. Tests: `pip install -r requirements-dev.txt && python -m pytest tests`.

## Docker
`docker compose up --build` starts three services in order:
1. `db` — `postgis/postgis:17-3.6-alpine` (PG 17 / PostGIS 3.6), data in the `pgdata` volume. On first init, `docker/postgres/initdb/` creates the `postgis` and `uuid-ossp` extensions.
2. `migrate` — runs `alembic upgrade head` once `db` is healthy, then exits. Runs on every `up`; a no-op when already at head.
3. `api` — starts only after `migrate` exits 0. Published on `127.0.0.1:8000` (loopback only; the reverse proxy sits in front).

Everything reads the single `.env`. Besides the app settings it needs:
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — container credentials. Compose builds the in-network `POSTGRES_CNX_STR_LOCAL` (`...@db:5432/...`) from them, overriding the host-oriented value in `.env`. Keep the password URL-safe. `ENV` must not be `dev`.
- `WEB_CONCURRENCY` — uvicorn workers (default 2). Each worker can hold up to 15 DB connections; keep `workers x 15` well under Postgres `max_connections` (50).
- `COMPOSE_FILE=docker-compose.yml` — **prod only**, so `docker compose up` skips the local override.

The prod VPS (6 vCPU / 12 GB) is shared with other apps, so the stack is capped at ~2.8 GB: memory limits of `db` 2g, `api` 768m, `migrate` 512m (runs briefly), and conservative Postgres settings (`shared_buffers=1GB`, `max_connections=50`). A container that exceeds its limit gets OOM-killed and restarted; check `docker compose ps` / `docker stats` if that happens.

`docker-compose.override.yml` (local, merged automatically) publishes Postgres on `127.0.0.1:55432`, uses stock Postgres settings instead of the prod tuning, and runs the api with `--reload` against bind-mounted `src/` and `alembic/`.

Common commands:
- `docker compose up -d --build` — start / redeploy (migrations run automatically).
- `docker compose logs -f api` / `docker compose logs migrate`.
- `docker compose run --rm migrate alembic revision --autogenerate -m "description"` — new migration (locally, lands in `alembic/versions/` via the bind mount).
- `docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"`.
- `docker compose down -v` — stop and **delete the database volume** (init scripts rerun on next `up`).

## Screenshots / Diagrams
- Architecture is captured in the Mermaid diagram above. (Add UI captures or architecture PNGs in this section if available.)

## Engineering Decisions
- Thin routers + dedicated services keep role checks/validation in sync with schema classes.
- Shared mixins (`ProfileImageMixin`, `ImagesMixin`) ensure S3 keys are always resolved into URLs at the schema level.
- Onboarding, editor/creator management, and article flows rely on reused SQLAlchemy models to keep relations consistent.

## Production Considerations
- **Rate limiting:** Redis-backed guards throttle high-volume creator/editor endpoints.
- **Caching:** Redis caches session metadata and lookup tables (cities, categories) to reduce DB queries.
- **Retries:** Background retries (UVicorn + async jobs) ensure eventual consistency for AWS uploads and article publishing.
- **Logging & Monitoring:** Structured logs via `src/config/logging.py`; middleware emits request traces. Hook monitoring dashboards to App logs/metrics.
- **Idempotency:** Creator onboarding and article edits check for existing records before upserting (guarding against duplicate links, categories, or cities).
- **Background jobs/Queue systems:** Queue-like patterns appear in article publish/reject flows; extend with Celery/RQ if bigger workloads arise.
- **Security:** All secrets live in `.env`. JWT and refresh secrets differ by environment and are rotated per deployment.
