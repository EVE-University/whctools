"""Tasks."""

from celery import shared_task

from allianceauth.services.hooks import get_extension_logger
from allianceauth.authentication.models import EveCharacter
from allianceauth.framework.api.evecharacter import get_user_from_evecharacter
from .models import Applications, Acl
from .utils import remove_in_process_application, remove_character_from_acls


logger = get_extension_logger(__name__)


@shared_task
def process_character_leaving_IVY(instance: EveCharacter):
    """Processes a character that is no longer in EveUni"""

    acls_character_is_on = Acl.objects.filter(characters=instance)

    if not acls_character_is_on or len(acls_character_is_on) == 0:
        #if the character is on no acls, then skip
        logger.debug(f"WHCTools Cleanup Task: Character has No Acls")
        return 
    
    character_applications = (
        EveCharacter.objects.filter(
                character_id=instance.character_id
        )
        .select_related("applications")
        .order_by("character_name")
    )

    if not character_applications:
        logger.warn(f"WHCTools Cleanup Task: {instance.character_name} is on acls {acls_character_is_on} but has no applications")
        # Potential desync state here - where character is on ACL lists but has no active/open Applications - this is a problem
        # people should be notified of the desync
        # discord notification?
        # remove from ACLs anyways?
        # dont care because Application is not the end all be all? its just the vehicle for getting onto ACLs?
        return
    
    user = get_user_from_evecharacter(character=instance)
    application_details = character_applications[0]
    existing_acl_state = application_details.member_state

    if existing_acl_state == Applications.MembershipStates.APPLIED:
        # If the character has applied to the community, remove their application
        remove_in_process_application(user, application_details)

    remove_character_from_acls(instance, acls_character_is_on, application_details, user, existing_acl_state)