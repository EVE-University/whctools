import datetime

from django.utils import timezone

from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from memberaudit.models import Character as MACharacter
from memberaudit.tasks import update_character as ma_update_character
# For MA 3.x, we have more granularity.
#  update_character_skills as ma_update_character_skills,
#  update_character_details as ma_update_character_details,
#  update_character_corporation_history as ma_update_character_corporation_history,
#)

from whctools import __title__
from whctools.models import Acl, ACLHistory, ApplicationHistory, Applications

from .aa3compat import get_all_related_characters_from_character
from .app_settings import TRANSIENT_REJECT

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


def remove_character_from_community(app, new_state, reason, reject_time):
    """
    remove a singular character application to a new_state for a given reason with a reject_time cooldown on a new application
    """
    try:

        app.member_state = new_state
        app.reject_reason = reason
        app.reject_timeout = timezone.now() + datetime.timedelta(days=int(reject_time))
        app.save()

    except Exception:
        logger.error(
            f"Failed to remove character from community app: {app} for reason {reason}"
        )


def remove_all_alts(acl_name, member_application, new_state, reason, reject_time):
    """
    Remove all alts from the acl and set their applications to the new state
    """
    all_characters = get_all_related_characters_from_character(
        member_application.eve_character
    )
    for char in all_characters:
        logger.debug(
            f"[Remove All Alts]- checking alt {char.character_name} for application"
        )
        app = Applications.objects.filter(eve_character=char)[0]
        if app:
            logger.debug(
                f"Removing alt named {app.eve_character.character_name} belonging to {member_application.eve_character.character_name}"
            )
            old_state = app.member_state
            remove_character_from_community(app, new_state, reason, reject_time)
            remove_character_from_acl(
                app.eve_character.character_id,
                acl_name,
                old_state,
                app.member_state,
                reason,
            )

    notification_names = ", ".join([char.character_name for char in all_characters])
    return notification_names


def remove_character_from_acl(char_id, acl_name, from_state, to_state, reason):
    """Helper function to remove a character from an acl"""

    acl_object = Acl.objects.filter(pk=acl_name)
    if acl_object:
        characters = acl_object[0].characters.all()
        for char in characters:
            if char.character_id == char_id:
                logger.debug(
                    f"Removing {char.character_name} form {acl_name} - setting to {Applications.MembershipStates(to_state).name} for {reason}"
                )
                acl_object[0].characters.remove(char)
                history_entry = ACLHistory(
                    character=char,
                    date_of_change=timezone.now(),
                    old_state=from_state,
                    new_state=to_state,
                    reason_for_change=reason,
                    changed_by="ToDo",
                    acl=acl_object[0],
                )
                history_entry.save()
                acl_object[0].changes.add(history_entry)
                return


def add_character_to_acl(acl_name, eve_character, old_state, new_state, reason):
    logger.debug(
        f"Adding {eve_character.character_name} to {acl_name} - setting to {Applications.MembershipStates(new_state).name} for reason of {reason}"
    )
    acl_obj = Acl.objects.get(pk=acl_name)
    if acl_obj:
        acl_obj.characters.add(eve_character)
        history_entry = ACLHistory(
            character=eve_character,
            date_of_change=timezone.now(),
            old_state=old_state,
            new_state=new_state,
            reason_for_change=reason,
            changed_by="Acceptance (todo)",
            acl=acl_obj,
        )
        history_entry.save()
        acl_obj.changes.add(history_entry)


def log_application_change(
    application: Applications,
    old_state=Applications.MembershipStates.NOTAMEMBER,
    reason=Applications.RejectionStates.NONE,
):
    log_user_application_change = ApplicationHistory(
        application=application,
        old_state=old_state,
        new_state=application.member_state,
        reject_reason=reason,
    )
    log_user_application_change.save()


def update_all_acls_for_character_leaving_alliance(
    character, acls_character_is_on, character_acl_application, user, existing_acl_state
):
    """
    Removes a character from all ACls they may be on, and informs the user for each character that they have been removed due to leaving the uni.
    """

    if character_acl_application is not None:
        remove_character_from_community(
            character_acl_application.Applications.MembershipStates.REJECTED,
            Applications.RejectionStates.LEFT_ALLIANCE,
            TRANSIENT_REJECT,
        )
        new_state = Applications.MembershipStates.REJECTED
    else:
        new_state = Applications.MembershipStates.NOTAMEMBER

    for acl in acls_character_is_on:
        logger.debug(f"Removing {character.character_name} from {acl.name}")
        remove_character_from_acl(
            character.character_id,
            acl.name,
            existing_acl_state,
            new_state,
            ACLHistory.ApplicationStateChangeReason.LEFT_UNI,
        )

        notify.danger(
            user,
            "WHC Community Status",
            f"Your status with {acl.name} on {character.character_name} has been removed\n:Reason: Character is no longer part of IVY or IVY-A",
        )


def remove_in_process_application(user, application_details):
    """
    For a character that has an un-accepted application still open, withdraw it.
    """
    try:
        application_details.member_state = Applications.MembershipStates.REJECTED
        application_details.reject_reason = Applications.RejectionStates.LEFT_ALLIANCE
        application_details.save()

        log_application_change(
            application=application_details,
            old_state=Applications.MembershipStates.APPLIED,
        )

        notify.danger(
            user,
            "WHC Application",
            f"Your character {application_details.eve_character.character_name} has left IVY or IVY-A and so your application to join WHC has been rejected automatically.",
        )
    except Exception:
        logger.error(
            f"Could not remove in process application of {application_details} for user: {user}"
        )


def generate_raw_copy_for_acl(acl_characters: dict):
    output = []
    for user in acl_characters.values():
        main_character_name = user["main"]["name"]
        output.append(f"Main: {main_character_name}")
        alts = user["alts"]
        for char in alts:
            output.append(f"Alt: {char['name']}")

        output.append("----")

    return "\n".join(output)

def force_update_memberaudit(eve_character):
    logger.debug(f"Forcing memberaudit update for character {eve_character}")
    try:
        ma_char = MACharacter.objects.get(eve_character=eve_character)
    except ObjectDoesNotExist:
        ma_char = None
    if ma_char is not None:
        ma_char.reset_update_section("skills")
        ma_char.reset_update_section("character_details")
        ma_char.reset_update_section("corporation_history")
        # For MA 3.x, there's more granularity in what to trigger
        #for ma_update in (ma_update_character_skills,
        #                  ma_update_character_details,
        #                  ma_update_character_corporation_details):
        #    ma_update.apply_async(
        ma_update_character.apply_async(
            kwargs={"character_pk": ma_char.pk, "force_update": True},
            priority=3, # 0-255, 0 highest priority (MA uses 3/5/7)
        )
    else:
        messages.warning(
            request,
            f"{eve_character.character_name} is not registered with Member Audit."
        )
