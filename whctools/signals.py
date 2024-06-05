# TODO @@@ Need a Signal check on member state change to Alumni to remove from all ACLS
# could add it to group assigner?
from django.dispatch import receiver

from django.db.models.signals import post_save
from django.core.exceptions import ObjectDoesNotExist

from allianceauth.authentication.models import EveCharacter
from .app_settings import IVY_LEAGUE_ALT_ALLIANCE, IVY_LEAGUE_ALLIANCE
from .tasks import process_character_leaving_IVY

from allianceauth.services.hooks import get_extension_logger
logger = get_extension_logger(__name__)



@receiver(post_save, sender=EveCharacter)
def leaves_uni(sender, instance, raw, using, update_fields, **kwargs):
    try:
        if instance.pk:
                
            
            if instance.alliance_id not in [IVY_LEAGUE_ALLIANCE, IVY_LEAGUE_ALT_ALLIANCE]:
                logger.debug(f"WHCTools Signal Character: {instance.character_name} has left IVY/IVY-A - spawning task to cleanup acl/applications")
                process_character_leaving_IVY.delay(instance)

        else:
            logger.debug(f"WHCTools Signal - Character is None")
            return
                
    except ObjectDoesNotExist as e:
        pass 
    except Exception as e:
        logger.error(e)
        pass 
