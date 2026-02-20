from ..models import Applications


def get_rejected_apps():
    chars_rejected = (
        Applications.objects.filter(member_state=Applications.MembershipStates.REJECTED)
        .select_related("eve_character__characteraudit")
        .order_by("last_updated")
        .reverse()
    )

    return chars_rejected
