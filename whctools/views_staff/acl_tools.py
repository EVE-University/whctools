from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from whctools import __title__
from whctools.models import ACLHistory, AclHistoryRequest, Applications

try:
    # Alliance auth 4.0 only
    from allianceauth.framework.api.evecharacter import (
        get_main_character_from_evecharacter,
        get_user_from_evecharacter,
    )
    from allianceauth.framework.api.user import get_all_characters_from_user
except Exception:
    # Alliance 3.0 backwards compatibility
    from whctools.aa3compat import (
        bc_get_all_characters_from_user as get_all_characters_from_user,
    )
    from whctools.aa3compat import (
        bc_get_main_character_from_evecharacter as get_main_character_from_evecharacter,
    )
    from whctools.aa3compat import (
        bc_get_user_from_eve_character as get_user_from_evecharacter,
    )


logger = LoggerAddTag(get_extension_logger(__name__), __title__)


def get_acl_actions_after_date(request, acl_pk):
    """
    returns the actions that need to be applied to an ACL in terms of 'latest state' with all subjects after a certain date.
    """
    logger.debug("POST request for acl history")
    form = AclHistoryRequest(request.POST)
    if form.is_valid():
        date_selected = form.cleaned_data.get("date_of_change")
        acl_history_entries = ACLHistory.objects.filter(
            date_of_change__gte=date_selected
        )
        logger.debug(f"Pulling ACL history after {date_selected} for {acl_pk}")
        parsed_acl_history = {}
        last_known_change = None
        for entry in acl_history_entries:
            if last_known_change is None or entry.date_of_change > last_known_change:
                new_state = Applications.MembershipStates(entry.new_state)
                if new_state in [
                    Applications.MembershipStates.NOTAMEMBER,
                    Applications.MembershipStates.APPLIED,
                    Applications.MembershipStates.REJECTED,
                ]:
                    action = "Remove"
                else:
                    action = "Add"
                last_known_change = entry.date_of_change
                parsed_acl_history[entry.character.character_name] = {
                    "date": entry.date_of_change,
                    "portrait_url": entry.character.portrait_url(32),
                    "name": entry.character.character_name,
                    "state": new_state.name,
                    "action": action,
                    "reason": entry.get_reason_for_change_display(),
                }

        parsed_acl_history = list(parsed_acl_history.values())
    return date_selected, parsed_acl_history


def get_mains_and_alts_sorted(acl_obj):
    """
    retrieves all the characters on an ACl and sorts them according to main and alts, alphabetical for mains with alts as a sub map.
    """
    members_on_acl = acl_obj.characters.all()
    mains_and_alts = {}
    for memb in members_on_acl:
        user_obj = get_user_from_evecharacter(memb)

        mains_and_alts.setdefault(user_obj.id, {})
        if "main" not in mains_and_alts[user_obj.id].keys():
            mains_and_alts[user_obj.id]["main"] = get_main_character_from_evecharacter(
                memb
            )

        mains_and_alts[user_obj.id].setdefault("alts", []).append(memb)
        mains_and_alts[user_obj.id].setdefault(
            "complete_alts", get_all_characters_from_user(user_obj)
        )

    # note to self - x[1] is not a list index, but a tuple index, becaus its .items(), returning (key, value)
    # and it has to be for it to remain a dict after sorting
    alphabetical_mains = dict(
        sorted(mains_and_alts.items(), key=lambda x: x[1]["main"].character_name)
    )

    for character in alphabetical_mains.values():

        character["main"] = {
            "name": character["main"].character_name,
            "corp": character["main"].corporation_name,
            "alliance": character["main"].alliance_name,
            "portrait_url": character["main"].portrait_url(32),
            "character_id": character["main"].id,
            "is_on_acl": character["main"].applications.member_state
            == Applications.MembershipStates.ACCEPTED,
        }
        character["alts"] = list(
            sorted(
                [
                    {
                        "name": m.character_name,
                        "corp": m.corporation_name,
                        "alliance": m.alliance_name,
                        "portrait_url": m.portrait_url(32),
                        "character_id": m.id,
                    }
                    for m in character["alts"]
                    if m.character_name != character["main"]["name"]
                ],
                key=lambda x: x["name"],
            )
        )

        acl_alt_names = [alt["name"] for alt in character["alts"]]

        character["complete_alts"] = list(
            sorted(
                [
                    {
                        "name": m.character_name,
                        "corp": m.corporation_name,
                        "alliance": m.alliance_name,
                        "portrait_url": m.portrait_url(32),
                    }
                    for m in character["complete_alts"]
                    if m.character_name not in acl_alt_names
                    and m.character_name != character["main"]["name"]
                ],
                key=lambda x: x["name"],
            )
        )

    return alphabetical_mains
