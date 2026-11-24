# handmaid_jew_and_acc

Online store for handmade jewelry and accessories — bilingual (Georgian / English),
guest checkout, built with Django, HTMX, Alpine.js and Tailwind CSS.

- Product & technical spec: [`docs/SPEC.md`](docs/SPEC.md)
- Conventions for contributors (and Claude): [`CLAUDE.md`](CLAUDE.md)

## Getting started (Windows PowerShell)

Requirements: [uv](https://docs.astral.sh/uv/) and Docker Desktop. No Node.js or GNU gettext needed.

```powershell
Copy-Item .env.example .env                      # then set DJANGO_SECRET_KEY, DEV_SUPERUSER_PASSWORD
uv sync                                          # Python 3.12 + dependencies
docker compose up -d db redis mailpit            # Postgres, Redis, mail catcher
uv run python scripts/tailwind.py build          # downloads the Tailwind CLI on first run
uv run python scripts/i18n.py compile            # Georgian translations (runs in Docker)
uv run python manage.py migrate
uv run python manage.py seed_demo
uv run python manage.py runserver
```

Open http://127.0.0.1:8000/ — it redirects to `/ka/`. While working on templates, run
`uv run python scripts/tailwind.py watch` in a second terminal.

| What | Where |
|---|---|
| Site | http://127.0.0.1:8000/ka/ · /en/ |
| Styleguide (DEBUG only) | http://127.0.0.1:8000/ka/_styleguide/ |
| Admin | http://127.0.0.1:8000/`ADMIN_URL` (from `.env`) |
| Emails (Mailpit) | http://127.0.0.1:8025/ |
| Health check | http://127.0.0.1:8000/healthz/ |

## Everyday commands

```powershell
uv run pytest                                    # tests
uv run ruff check . ; uv run ruff format .       # lint + format (also run by pre-commit)
uv run python scripts/i18n.py make               # extract strings into locale/ka/…/django.po
uv run python scripts/i18n.py compile            # compile translations
docker compose --profile app up --build          # production-like run (gunicorn + worker) on :8000
```
