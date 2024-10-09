import datetime

from django.utils import timezone

from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from memberaudit.models import Character as MACharacter
#from memberaudit.tasks import update_character as ma_update_character
# For MA 3.x, we have more granularity.
from memberaudit.tasks import update_character_skills as ma_update_character_skills

from whctools import __title__
from whctools.app_settings import ALLOWED_ALLIANCES
from whctools.models import Acl, ACLHistory, ApplicationHistory, Applications

from .aa3compat import get_all_related_characters_from_character
from allianceauth.framework.api.evecharacter import (
    get_user_from_evecharacter,
    get_main_character_from_evecharacter,
)
from .app_settings import TRANSIENT_REJECT

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


def is_main_eve_character(eve_character):
    main_character = get_main_character_from_evecharacter(eve_character)
    if (main_character is not None) and (main_character == eve_character):
        return True
    return False

def is_character_in_allowed_corp(eve_character):
    return (eve_character.alliance_id in ALLOWED_ALLIANCES)

def get_corp_requirements_message():
    """
    Returns a human-readable string describing the corp criteria for an alt character.
    """
    # Since we can have arbitrarily complex conditions, it's useful to have a programmatically-defined descriptor.
    # FIXME: sync with app_settings
    return "Character must be in either the Ivy League or Ivy League Alt Alliance."


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
        user = None
        characters = acl_object[0].characters.all()
        for char in characters:
            if char.character_id == char_id:
                user = get_user_from_evecharacter(char)
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
        # Character has been removed, if it existed in the ACL.
        # If this was the last character, also remove the user from all the
        # ACL's associated groups.
        characters = acl_object[0].characters.all()
        if len(characters)==0 and user is not None:
            for group in acl_object[0].groups.all():
                user.groups.remove(group)
          

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
        user = get_user_from_evecharacter(eve_character)
        for group in acl_obj.groups.all():
            user.groups.add(group)
        

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


def synchronize_groups_from_acl(acl_name):
    acl_result = Acl.objects.filter(pk=acl_name)
    if not acl_result:
        logger.error(f"Attempted to synchronize groups from nonexistent ACL '{acl_name}'")
        return
    acl = acl_result[0]
    # Add characters in the ACL that should be in groups
    all_authorized_users = set([])
    for char in acl.characters.all():
        user = get_user_from_evecharacter(char)
        all_authorized_users.add(user)
        for group in acl.groups.all():
            user.groups.add(group)
    # Remove characters not in the ACL that shouldn't be in groups
    #import pdb; pdb.set_trace()
    for group in acl.groups.all():
        group_users = group.user_set.all()
        invalid_users = set(group_users) - all_authorized_users
        for user in invalid_users:
            user.groups.remove(group)


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


def generate_raw_copy_for_acl(sorted_char_list: list):
    output = []
    for character in sorted_char_list:
        if character['is_main']:
            output.append(f"Main: {character['name']}")
        else:
            output.append(f"Alt: {character['name']}")

    return "\n".join(output)

def force_update_memberaudit(eve_character):
    logger.debug(f"Forcing memberaudit update for character {eve_character}")
    try:
        ma_char = MACharacter.objects.get(eve_character=eve_character)
    except ObjectDoesNotExist:
        ma_char = None
    if ma_char is not None:
        ma_char.reset_update_section("skills")
        ma_update_character_skills.apply_async(
            kwargs={"character_pk": ma_char.pk, "force_update": True},
            priority=3)
    else:
        messages.warning(
            request,
            f"{eve_character.character_name} is not registered with Member Audit."
        )

def get_last_ma_update_time(eve_character):
    '''Return a datetime for when memberaudit was last successfully updated with skill data'''

    logger.info(f"get_last_ma_update_time")
    try:
        ma_char = eve_character.memberaudit_character
        # Also check it wasn't an error last time
        is_status_okay = ma_char.is_update_status_ok()
        last_ma_update = ma_char.update_status_set.get(
            section=MACharacter.UpdateSection.SKILLS
        ).update_finished_at
        if is_status_okay:
            return last_ma_update
    except Exception as e:
        pass
    # If something goes wrong, return an unreasonably old datetime.
    return datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)
