"""Tasks."""

from celery import shared_task

from allianceauth.services.hooks import get_extension_logger

logger = get_extension_logger(__name__)


@shared_task
def my_task():
    """An whctools task."""
