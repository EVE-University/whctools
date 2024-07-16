"""App settings."""

from django.conf import settings

TRANSIENT_REJECT = getattr(settings, "WHCTOOLS_TRANSIENT_REJECT", 2)

SHORT_REJECT = getattr(settings, "WHCTOOLS_SHORT_REJECT", 5)

MEDIUM_REJECT = getattr(settings, "WHCTOOLS_MEDIUM_REJECT", 30)

LARGE_REJECT = getattr(settings, "WHCTOOLS_LARGE_REJECT", 365)

LIMIT_TO_ALLIANCES = getattr(settings, "WHCTOOLS_LIMIT_TO_ALLIANCES", False)

ALLOWED_ALLIANCES = getattr(settings, "WHC_ALLIANCES", [937872513, 99010193])
