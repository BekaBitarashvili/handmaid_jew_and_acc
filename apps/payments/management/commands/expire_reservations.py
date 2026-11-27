from django.core.management.base import BaseCommand

from apps.payments.services import expire_overdue


class Command(BaseCommand):
    help = (
        "Release pieces held by unpaid orders whose 15 minutes are over "
        "(huey does this every minute)."
    )

    def handle(self, *args, **options):
        count = expire_overdue()
        self.stdout.write(f"{count} order(s) expired.")
