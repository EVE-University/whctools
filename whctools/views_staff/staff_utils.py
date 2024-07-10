from whctools.app_settings import (
    LARGE_REJECT,
    MEDIUM_REJECT,
    SHORT_REJECT,
    TRANSIENT_REJECT,
)


def build_default_staff_context(page: str) -> dict:
    return {
        "page": page,
        "reject_timers": {
            "large_reject": LARGE_REJECT,
            "medium_reject": MEDIUM_REJECT,
            "short_reject": SHORT_REJECT,
            "transient_reject": TRANSIENT_REJECT,
        },
    }
