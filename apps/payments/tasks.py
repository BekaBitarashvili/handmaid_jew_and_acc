from huey import crontab
from huey.contrib.djhuey import db_periodic_task

from .services import expire_overdue


@db_periodic_task(crontab(minute="*"))
def expire_reservations() -> int:
    """Every minute: release pieces held by orders not paid within 15 minutes (SPEC §6.5)."""
    return expire_overdue()
