from django.utils import timezone

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from whctools import __title__
from whctools.models import Acl, ACLHistory, Applications, ApplicationHistory

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


def log_application_change(application, old_state=Applications.MembershipStates.NOTAMEMBER, new_state=Applications.MembershipStates.NOTAMEMBER, reason=Applications.RejectionStates.NONE):
    log_user_application_change = ApplicationHistory(
        application=application,
        old_state=old_state ,
        new_state=new_state,
        reject_reason=reason
    )
    log_user_application_change.save()