"""Seed a local development database with demo data. Safe to run repeatedly.

    uv run python manage.py seed_demo

Creates the SiteSettings row, a dev superuser, a demo catalog (categories,
stones, materials, ~20 products with variants and placeholder photos) and
delivery options. Later phases add steps to `seeders`.
"""

import sys
from collections.abc import Callable
from getpass import getpass

import environ
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import (
    Category,
    Material,
    Product,
    ProductImage,
    ProductVariant,
    SkuSequence,
    Stone,
)
from apps.catalog.seed import seed_catalog
from apps.core.models import SiteSettings
from apps.orders.seed import seed_delivery_options
from apps.pages.models import HeroSlide
from apps.pages.seed import seed_hero
from apps.promotions.models import Sale
from apps.promotions.seed import seed_sale

env = environ.Env()


class Command(BaseCommand):
    help = "Seed demo data for local development (refuses to run when DEBUG is off)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-catalog",
            action="store_true",
            help="Delete the demo catalog, sales and hero slides first (dev only), then reseed.",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Never prompt; skip the superuser if DEV_SUPERUSER_PASSWORD is not set.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DEBUG=True (development).")
        self.interactive = not options["no_input"] and sys.stdin.isatty()
        if options["reset_catalog"]:
            self.reset_catalog()

        seeders: list[tuple[str, Callable[[], str]]] = [
            ("Site settings", self.seed_site_settings),
            ("Superuser", self.seed_superuser),
            ("Catalog", seed_catalog),
            ("Hero slides", seed_hero),
            ("Sale", seed_sale),
            ("Delivery options", seed_delivery_options),
        ]
        for label, seeder in seeders:
            with transaction.atomic():
                result = seeder()
            self.stdout.write(f"{label}: {result}")
        self.stdout.write(self.style.SUCCESS("Demo data ready."))

    @transaction.atomic
    def reset_catalog(self) -> None:
        for model in (Sale, HeroSlide, ProductImage, ProductVariant):
            model.objects.all().delete()
        Product.objects.all().delete()
        Category.objects.filter(parent__isnull=False).delete()
        for model in (Category, Stone, Material, SkuSequence):
            model.objects.all().delete()
        self.stdout.write("Demo catalog, sales and hero slides removed.")

    def seed_site_settings(self) -> str:
        existed = SiteSettings.objects.filter(pk=SiteSettings.SINGLETON_PK).exists()
        site = SiteSettings.load()
        # Obviously fake demo contacts (dev only), filled only where the owner left blanks.
        demo = {
            "contact_phone": "+995 555 00 00 00",
            "contact_email": "hello@example.com",
            "contact_address": "Tbilisi (demo address)",
            "instagram_url": "https://instagram.com/example",
            "pinterest_url": "https://pinterest.com/example",
            "facebook_url": "https://facebook.com/example",
        }
        filled = [field for field, value in demo.items() if not getattr(site, field)]
        for field in filled:
            setattr(site, field, demo[field])
        if filled:
            site.save(update_fields=filled)
        state = "kept" if existed else "created"
        return f"{state} ({site.brand_name}); demo contacts: {len(filled)} filled"

    def seed_superuser(self) -> str:
        user_model = get_user_model()
        username = env("DEV_SUPERUSER_USERNAME", default="admin")
        email = env("DEV_SUPERUSER_EMAIL", default="admin@example.com")

        if user_model.objects.filter(username=username).exists():
            return f"kept '{username}' (password unchanged)"

        password = env("DEV_SUPERUSER_PASSWORD", default="")
        if not password and self.interactive:
            password = self._prompt_password(username)
        if not password:
            return self.style.WARNING(
                "skipped — set DEV_SUPERUSER_PASSWORD in .env or run interactively"
            )

        user_model.objects.create_superuser(username=username, email=email, password=password)
        return f"created '{username}'"

    def _prompt_password(self, username: str) -> str:
        while True:
            password = getpass(f"Password for dev superuser '{username}': ")
            if password != getpass("Again: "):
                self.stderr.write("Passwords don't match.")
                continue
            try:
                validate_password(password)
            except ValidationError as error:
                self.stderr.write(" ".join(error.messages))
                continue
            return password
