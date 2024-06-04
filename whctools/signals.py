# TODO @@@ Need a Signal check on member state change to Alumni to remove from all ACLS
# could add it to group assigner?
from django.dispatch import receiver

from django.db.models.signals import post_save
from django.core.exceptions import ObjectDoesNotExist

from allianceauth.authentication.models import EveCharacter
from allianceauth.framework.api.evecharacter import get_user_from_evecharacter
from allianceauth.notifications import notify
from .models import Applications, Acl, ACLHistory
from .app_settings import IVY_LEAGUE_ALT_ALLIANCE, IVY_LEAGUE_ALLIANCE, TRANSIENT_REJECT
from .utils import remove_character_from_acl
from django.utils import timezone
import datetime

from allianceauth.services.hooks import get_extension_logger
logger = get_extension_logger(__name__)



@receiver(post_save, sender=EveCharacter)
def leaves_uni(sender, instance, raw, using, update_fields, **kwargs):
    try:
        if instance.pk:
            character = EveCharacter.objects.get(pk=instance.pk)

            if character.alliance_id not in [IVY_LEAGUE_ALLIANCE, IVY_LEAGUE_ALT_ALLIANCE]:

                acls_character_is_on = Acl.objects.filter(characters=character)

                if not acls_character_is_on or len(acls_character_is_on) == 0:
                    #if the character is on no acls, then skip
                    return 
                
                character_acl_application = (
                    EveCharacter.objects.filter(
                         character_id=character.character_id
                    )
                    .select_related("applications")
                    .order_by("character_name")
                )

                if not character_acl_application:
                    #if somehow the character, despite being on acls, has an open application...

                    # do something here!!!
                    # discord notify probably
                    return
                
                user = get_user_from_evecharacter(character=character)
                application_details = character_acl_application[0]
                existing_acl_state = application_details.member_state

                if existing_acl_state == Applications.MembershipStates.APPLIED:
                    # If the character has applied to the community, remove their application
                    remove_in_process_application(user, application_details)
                    return

                if existing_acl_state != Applications.MembershipStates.ACCEPTED:
                    # If the character is not a part of the community, just skip
                    return

                remove_character_from_acls(character, acls_character_is_on, character_acl_application, user, application_details, existing_acl_state)
                
                
    except ObjectDoesNotExist as e:
        pass # no config for this state so skip.
    except Exception as e:
        logger.error(e)
        pass 

def remove_character_from_acls(character, acls_character_is_on, character_acl_application, user, application_details, existing_acl_state):
    """
    Removes a character from all ACls they may be on, and informs the user for each character that they have been removed due to leaving the uni.
    """
    character_acl_application.member_state == Applications.MembershipStates.REJECTED
    application_details.reject_reason = Applications.RejectionStates.LEFT_ALLIANCE
    application_details.save()

    for acl in acls_character_is_on:
        logger.debug(f"Removing {character.character_name} from {acl.name}")
        remove_character_from_acl(character.character_id, acl.name, existing_acl_state, character_acl_application.member_state, ACLHistory.ApplicationStateChangeReason.LEFT_UNI )
        application_details.reject_timeout = timezone.now() + datetime.timedelta(
                        days=int(TRANSIENT_REJECT)
                    )

        notify.danger(
                        user,
                        "WHC Community Status",
                        f"Your status in the WHC Community on {character.character_name} has been removed\n:Reason: Character is no longer part of IVY or IVY-A",
                    )

def remove_in_process_application(user, application_details):
    """
    For a character that has an un-accepted application still open, with draw it.
    """
    application_details.member_state == Applications.MembershipStates.REJECTED
    application_details.reject_reason = Applications.RejectionStates.LEFT_ALLIANCE
    application_details.save()
                    # no time penalty here
                    
    notify.danger(
                        user,
                        "WHC Application",
                        f"Your character {application_details.eve_character.character_name} has left IVY or IVY-A and so your application to join WHC has been rejected automatically.",
                    ) # shits fucked... Don't worry about it...  Sometimes you just have to lick the stamp and send it.