from django.utils import timezone
import datetime

from allianceauth.services.hooks import get_extension_logger

from app_utils.logging import LoggerAddTag

from whctools import __title__
from whctools.models import Acl, ACLHistory, Applications, ApplicationHistory
from allianceauth.notifications import notify
from .app_settings import TRANSIENT_REJECT

# 3.0 backwards compatibility
from allianceauth.eveonline.models import EveCharacter
from django.contrib.auth.models import User
from allianceauth.authentication.models import CharacterOwnership

logger = LoggerAddTag(get_extension_logger(__name__), __title__)

def remove_character_from_acl(char_id, acl_name, from_state, to_state, reason):
    """Helper function to remove a character from an acl"""


    acl_object = Acl.objects.filter(pk=acl_name)
    if acl_object:
        characters = acl_object[0].characters.all()
        for char in characters:
            if char.character_id == char_id:
                logger.debug(f"Removing {char.character_name} form {acl_name} - setting to {Applications.MembershipStates(to_state).name} for {reason.name}")
                acl_object[0].characters.remove(char)
                history_entry = ACLHistory(
                    character=char,
                    date_of_change=timezone.now(),
                    old_state = from_state,
                    new_state = to_state, 
                    reason_for_change = reason,
                    changed_by = "ToDo",
                    acl=acl_object[0]
                )
                history_entry.save()
                acl_object[0].changes.add(history_entry)

def add_character_to_acl(acl_name, eve_character, old_state, new_state, reason):
    logger.debug(f"Adding {eve_character.character_name} to {acl_name} - setting to {Applications.MembershipStates(new_state).name} for {reason.name}")
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
                acl=acl_obj
            )
        history_entry.save()
        acl_obj.changes.add(history_entry)


def log_application_change(application:Applications, old_state=Applications.MembershipStates.NOTAMEMBER, reason=Applications.RejectionStates.NONE):
    log_user_application_change = ApplicationHistory(
        application=application,
        old_state=old_state ,
        new_state=application.member_state,
        reject_reason=reason
    )
    log_user_application_change.save()



def remove_character_from_acls(character, acls_character_is_on, character_acl_application, user, existing_acl_state):
    """
    Removes a character from all ACls they may be on, and informs the user for each character that they have been removed due to leaving the uni.
    """

    if character_acl_application is not None:
        character_acl_application.member_state = Applications.MembershipStates.REJECTED
        character_acl_application.reject_reason = Applications.RejectionStates.LEFT_ALLIANCE
        character_acl_application.reject_timeout = timezone.now() + datetime.timedelta(
                    days=int(TRANSIENT_REJECT)
                )
        character_acl_application.save()
        new_state = Applications.MembershipStates.REJECTED
    else:
        new_state = Applications.MembershipStates.NOTAMEMBER

    for acl in acls_character_is_on:
        logger.debug(f"Removing {character.character_name} from {acl.name}")
        remove_character_from_acl(character.character_id, acl.name, existing_acl_state, new_state, ACLHistory.ApplicationStateChangeReason.LEFT_UNI )


        notify.danger(
            user,
            "WHC Community Status",
            f"Your status with {acl.name} on {character.character_name} has been removed\n:Reason: Character is no longer part of IVY or IVY-A",
        )

def remove_in_process_application(user, application_details):
    """
    For a character that has an un-accepted application still open, withdraw it.
    """
    application_details.member_state = Applications.MembershipStates.REJECTED
    application_details.reject_reason = Applications.RejectionStates.LEFT_ALLIANCE
    application_details.save()
                    
    log_application_change(
        application=application_details,
        old_state=Applications.MembershipStates.APPLIED)
                    
    notify.danger(
        user,
        "WHC Application",
        f"Your character {application_details.eve_character.character_name} has left IVY or IVY-A and so your application to join WHC has been rejected automatically.",
    ) # shits fucked... Don't worry about it...  Sometimes you just have to lick the stamp and send it.



def bc_get_main_character_name_from_user(user:User):
    """
    3.0 Backwards compatible version of framework.api.user.get_main_character_name_from_user
    """
    if user is None:
        return None

    try:
        main_character = user.profile.main_character
    except AttributeError:
        return None

    return main_character
    
def bc_get_all_characters_from_user(user:User):
    """
    3.0 Backwards compatible version of framework.api.user.get_all_characters_from_user
    """
    if user is None:
        return []

    try:
        characters = [
            char.character for char in CharacterOwnership.objects.filter(user=user)
        ]
    except AttributeError:
        return []

    return characters

def bc_get_user_from_eve_character(character:EveCharacter):
    """
    3.0 Backwards compatible version of framework.api.evecharacter import get_user_from_evecharacter
    """
    try:
        userprofile = character.character_ownership.user.profile
    except (
        AttributeError,
        EveCharacter.character_ownership.RelatedObjectDoesNotExist,
        CharacterOwnership.user.RelatedObjectDoesNotExist,
    ):
        # replaces get_sentinel_user wrapper from 4.0
        # basically getting a user object of some kind to return, even if its an 'empty' one
        return User.objects.get_or_create(username="deleted")[0]


    return userprofile.user


def bc_get_main_character_from_evecharacter(character:EveCharacter):
    """
    3.0 Backwards compatible version of framework.api.evecharacter import get_main_character_from_evecharacter
    """
    try:
        userprofile = character.character_ownership.user.profile
    except (
        AttributeError,
        EveCharacter.character_ownership.RelatedObjectDoesNotExist,
        CharacterOwnership.user.RelatedObjectDoesNotExist,
    ):
        return None

    return userprofile.main_character
