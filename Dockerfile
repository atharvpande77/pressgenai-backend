# syntax=docker/dockerfile:1

# ---- builder: compile wheels (psycopg2 has no binary wheel) ----
FROM python:3.12.8-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir -r requirements.txt -w /wheels


# ---- runtime ----
FROM python:3.12.8-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/* && rm -rf /wheels

RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app src ./src
USER app

EXPOSE 8000

# Shell form so WEB_CONCURRENCY expands; exec keeps uvicorn as PID 1 for signals.
CMD exec uvicorn src.app:app --host 0.0.0.0 --port 8000 \
    --workers ${WEB_CONCURRENCY:-2} \
    --proxy-headers --forwarded-allow-ips='*'
