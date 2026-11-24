# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12

# --- deps: Python + runtime dependencies in /opt/venv ------------------------
FROM python:${PYTHON_VERSION}-slim AS deps
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# --- tools: dev deps + GNU gettext, used with the source bind-mounted -------
# Runs makemessages/compilemessages for Windows hosts (scripts/i18n.py).
FROM deps AS tools
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --no-install-project

# --- build: compile translations and collect static files -------------------
FROM deps AS build
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*
COPY . .
# Placeholder values only satisfy prod settings at build time; nothing connects anywhere.
ENV DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_SECRET_KEY=build-only \
    DJANGO_ALLOWED_HOSTS=localhost \
    DATABASE_URL=sqlite:////tmp/build.sqlite3 \
    AWS_ACCESS_KEY_ID=build \
    AWS_SECRET_ACCESS_KEY=build \
    AWS_STORAGE_BUCKET_NAME=build
RUN python manage.py compilemessages --ignore=.venv \
    && python manage.py collectstatic --noinput

# --- runtime: slim image, non-root -----------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod
RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=deps /opt/venv /opt/venv
COPY --from=build --chown=app:app /app /app
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
