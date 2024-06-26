"""App settings."""

from django.conf import settings

TRANSIENT_REJECT = getattr(settings, "WHCTOOLS_TRANSIENT_REJECT", 2)

SHORT_REJECT = getattr(settings, "WHCTOOLS_SHORT_REJECT", 5)

MEDIUM_REJECT = getattr(settings, "WHCTOOLS_MEDIUM_REJECT", 30)

LARGE_REJECT = getattr(settings, "WHCTOOLS_LARGE_REJECT", 365)

IVY_LEAGUE_ALLIANCE = 937872513

IVY_LEAGUE_ALT_ALLIANCE = 99010193