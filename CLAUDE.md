# CLAUDE.md — Handmade Jewelry Store

Read `docs/SPEC.md` before any non-trivial task. It is the single source of truth
for scope, data model, flows and the design system. If a request conflicts with
SPEC.md, ask before deviating; if a decision is made, update SPEC.md in the same change.

## Project in one paragraph
A bilingual (Georgian `ka` default, English `en`) online boutique for handmade
jewelry and accessories (natural-stone & bead necklaces, earrings, bracelets,
vintage pieces, knitted headscarves). Most items are one-of-a-kind (stock = 1).
Guest checkout only (no customer accounts in MVP). Payments: Bank of Georgia (BOG)
and TBC via their hosted payment pages. Delivery is handled manually by the owner.
The owner manages everything from a mobile-friendly admin. The visual identity
must feel like a quiet, editorial, vintage-modern jewelry atelier — never like a
generic template shop.

## Stack (do not change without asking)
- Python 3.12, Django 5.x, PostgreSQL 16
- HTMX + Alpine.js (no SPA framework), Tailwind CSS via the **standalone CLI** (no Node.js)
- Admin: Django Admin + `django-unfold`
- i18n: Django i18n (`gettext`) for UI strings, `django-modeltranslation` for content
- Background jobs: `huey` (Redis) — emails, SMS, reservation expiry
- Media: S3-compatible storage (`django-storages`) + `easy-thumbnails` (Pillow writes WebP/AVIF natively)
- Python is pinned via `.python-version` (3.12); Django 5.x does not support newer versions
- Tooling: `uv`, `ruff`, `pytest` + `pytest-django`, `factory_boy`, `pre-commit`
- Errors: Sentry. Deploy: Docker + docker-compose (web, db, redis, worker), Caddy/Nginx

## Conventions
- All code, comments, commit messages, docs: **English**. All user-facing strings wrapped in `gettext`; Georgian translations in `locale/ka/`.
- Apps live in `apps/`: `core`, `catalog`, `cart`, `orders`, `payments`, `promotions`, `wishlist`, `pages`.
- Money: stored as integers in **tetri** (`PositiveIntegerField`, 1 GEL = 100 tetri). Never use float. Currency is GEL only.
- Business logic in `services.py` per app, not in views or models' `save()`. Views stay thin.
- Any stock change goes through `catalog.services.inventory` using `select_for_update()` inside `transaction.atomic()`.
- Payment providers implement `payments.providers.base.PaymentProvider`; never store card data.
- Templates: `templates/<app>/...`, reusable pieces in `templates/components/`. HTMX partials suffixed `_partial.html`.
- Every feature ships with tests (services + critical views). Run `ruff check`, `ruff format`, `pytest` before declaring done.
- Secrets only via environment variables (`django-environ`), `.env.example` kept up to date.

## Commands
```
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
uv run pytest
uv run ruff check . && uv run ruff format .
docker compose up -d db redis mailpit
uv run python scripts/tailwind.py watch      # CSS in dev (`build` = minified, used by Docker/CI)
uv run python scripts/i18n.py make|compile   # gettext runs inside Docker (no gettext on Windows)
uv run python manage.py seed_demo            # dev data, idempotent
```
Local services use `127.0.0.1`, not `localhost` (on Windows `localhost` tries IPv6 first: +5s per DB connection).
Styleguide (DEBUG only): `/ka/_styleguide/`, `/en/_styleguide/`.

## Design non-negotiables (details in SPEC.md §9)
- Generous whitespace, slow & subtle motion, no auto-rotating carousels, no pop-ups on load.
- Fonts must render Georgian script in the intended style — verify every font with Georgian text.
- Photography leads; UI recedes. Max 1 accent color (muted gold) used sparingly.
- Mobile-first; every page tested at 375px, 768px, 1280px.
- Accessibility: WCAG 2.1 AA contrast, keyboard navigable, `prefers-reduced-motion` respected.

## Working style
- Work in the phases in SPEC.md §13. Don't build Phase 3 features during Phase 1.
- Small, reviewable commits. Propose a plan before large refactors.
- When unsure about business rules, ask — do not invent policies (returns, shipping prices, legal text).
