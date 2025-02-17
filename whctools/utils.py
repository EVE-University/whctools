import datetime
import os
import requests

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
            remove_character(
                acl_name,
                app.eve_character,
                old_state,
                app.member_state,
                reason,
            )

    notification_names = ", ".join([char.character_name for char in all_characters])
    return notification_names

def remove_character(acl_name, eve_character, from_state, to_state, reason):
    remove_character_from_acl(acl_name, eve_character, from_state, to_state, reason)
    remove_character_from_wanderer(acl_name, eve_character.character_id, eve_character.character_name)

def remove_character_from_acl(acl_name, eve_character, from_state, to_state, reason):
    """Helper function to remove a character from an acl"""

    acl_object = Acl.objects.filter(pk=acl_name)
    if acl_object:
        user = None
        characters = acl_object[0].characters.all()
        for char in characters:
            if char.character_id == eve_character.character_id:
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

def remove_character_from_wanderer(acl_name, eve_character_id, eve_character_name="Unknown"):
    wanderer_acl_id = os.getenv("WANDERER_ACL_ID", None)
    wanderer_acl_token = os.getenv("WANDERER_ACL_TOKEN", None)
    if wanderer_acl_id is None or wanderer_acl_token is None:
        logger.error(f"No WANDERER_ACL_ID or WANDERER_ACL_TOKEN environment variables found. Unable to issue API commands.")
        return
    logger.debug(
        f"Removing {eve_character_name} from Wanderer ACL {wanderer_acl_id}"
    )
    # Remove character
    api_url = f"https://wanderer.eveuniversity.org/api/acls/{wanderer_acl_id}/members/{eve_character_id}"
    headers = {"Authorization": f"Bearer {wanderer_acl_token}"}
    r = requests.delete(api_url, headers=headers)
    if r.status_code!=200:
        logger.error(f"Unable to remove character {eve_character_name} from Wanderer ACL {wanderer_acl_id}: {r.status_code}")

def add_character(acl_name, eve_character, old_state, new_state, reason):
    add_character_to_acl(acl_name, eve_character, old_state, new_state, reason)
    add_character_to_wanderer(acl_name, eve_character.character_id, eve_character.character_name)

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

def add_character_to_wanderer(acl_name, eve_character_id, eve_character_name="Unknown"):
    wanderer_acl_id = os.getenv("WANDERER_ACL_ID", None)
    wanderer_acl_token = os.getenv("WANDERER_ACL_TOKEN", None)
    if wanderer_acl_id is None or wanderer_acl_token is None:
        logger.error(f"No WANDERER_ACL_ID or WANDERER_ACL_TOKEN environment variables found. Unable to issue API commands.")
        return
    logger.debug(
        f"Adding {eve_character_name} to Wanderer ACL {wanderer_acl_id}"
    )
    # Add character
    api_url = f"https://wanderer.eveuniversity.org/api/acls/{wanderer_acl_id}/members"
    headers = {"Authorization": f"Bearer {wanderer_acl_token}"}
    payload = {
        "member": {
            "eve_character_id": str(eve_character_id),
            "role": "member",
        }
    }
    r = requests.post(api_url, headers=headers, json=payload)
    if r.status_code!=200:
        logger.error(f"Unable to add character {eve_character_name} to Wanderer ACL {wanderer_acl_id}: {r.status_code}")


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
        remove_character(
            acl.name,
            character.character_id,
            existing_acl_state,
            new_state,
            ACLHistory.ApplicationStateChangeReason.LEFT_UNI,
        )

        notify.danger(
            user,
            "WHC Community Status",
            f"Your status with {acl.name} on {character.character_name} has been removed\n:Reason: Character is no longer part of IVY or IVY-A",
        )


def sync_groups_with_acl_helper(acl_name):
    acl_result = Acl.objects.filter(pk=acl_name)
    if not acl_result:
        logger.error(f"Attempted to synchronize groups with nonexistent ACL '{acl_name}'")
        return
    logger.debug(f"Attempting to synchronize groups with ACL '{acl_name}'")
    acl = acl_result[0]
    # Add characters in the ACL that should be in groups
    all_authorized_users = set([])
    for char in acl.characters.all():
        user = get_user_from_evecharacter(char)
        all_authorized_users.add(user)
        for group in acl.groups.all():
            user.groups.add(group)
    # Remove characters not in the ACL that shouldn't be in groups
    for group in acl.groups.all():
        group_users = group.user_set.all()
        invalid_users = set(group_users) - all_authorized_users
        for user in invalid_users:
            user.groups.remove(group)

def sync_wanderer_with_acl_helper(acl_name):
    acl_result = Acl.objects.filter(pk=acl_name)
    if not acl_result:
        logger.error(f"Attempted to synchronize wanderer with nonexistent ACL '{acl_name}'")
        return
    logger.debug(f"Attempting to synchronize wanderer with ACL '{acl_name}'")
    acl = acl_result[0]

    # Grab Wanderer information from environment
    wanderer_acl_id = os.getenv("WANDERER_ACL_ID", None)
    wanderer_acl_token = os.getenv("WANDERER_ACL_TOKEN", None)
    if wanderer_acl_id is None or wanderer_acl_token is None:
        logger.error(f"No WANDERER_ACL_ID or WANDERER_ACL_TOKEN environment variables found. Unable to issue API commands.")
        return

    # Characters on wanderer may not by on auth and vice-versa. To make logging
    # informative, we grab the names from both sources and unify them.
    id_to_name = {}

    # Pull set of all characters on Auth ACL
    auth_char_tuples = set([(int(char.character_id), char.character_name) for char in acl.characters.all()])
    auth_char_ids = set([t[0] for t in auth_char_tuples])
    id_to_name.update(dict(auth_char_tuples))

    # Pull set of all characters on Wanderer ACL
    api_url = f"https://wanderer.eveuniversity.org/api/acls/{wanderer_acl_id}"
    headers = {"Authorization": f"Bearer {wanderer_acl_token}"}
    r = requests.get(api_url, headers=headers)
    if r.status_code!=200:
        logger.error(f"Unable to add character {eve_character.character_name} to Wanderer ACL {wanderer_acl_id}: {r.status_code}")
        return
    response = r.json()
    try:
        members = response["data"]["members"]
    except KeyError:
        logger.error(f"Malformed response received from Wanderer server: {response}")
        return
    wanderer_char_tuples = [(int(member["eve_character_id"]),member["name"]) for member in members]
    if len(wanderer_char_tuples)==0:
        logger.warning(f"Zero members received from Wanderer ACL. This is almost certainly wrong. *Someone* should have access. Aborting sync.")
        return
    wanderer_char_ids = set([t[0] for t in wanderer_char_tuples])
    id_to_name.update(dict(wanderer_char_tuples))

    # Add characters in the ACL that should be in groups
    chars_to_add = list(auth_char_ids - wanderer_char_ids)
    for char_id in chars_to_add:
        add_character_to_wanderer(acl_name, char_id, id_to_name[char_id])
    # Remove characters not in the ACL that shouldn't be in groups
    chars_to_remove = list(wanderer_char_ids - auth_char_ids)
    for char_id in chars_to_remove:
        remove_character_from_wanderer(acl_name, char_id, id_to_name[char_id])


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
