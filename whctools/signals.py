# TODO @@@ Need a Signal check on member state change to Alumni to remove from all ACLS
# could add it to group assigner?
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_save
from django.dispatch import receiver

from allianceauth.authentication.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger

from .app_settings import ALLOWED_ALLIANCES
from .tasks import process_character_leaving_IVY

logger = get_extension_logger(__name__)


@receiver(post_save, sender=EveCharacter)
def leaves_uni(sender, instance, raw, using, update_fields, **kwargs):
    try:
        if instance.pk:

            if instance.alliance_id not in ALLOWED_ALLIANCES:
                logger.debug(
                    f"WHCTools Signal Character: {instance.character_name} has left IVY/IVY-A - spawning task to cleanup acl/applications"
                )
                process_character_leaving_IVY.delay(instance)

        else:
            logger.debug("WHCTools Signal - Character is None")
            return

    except ObjectDoesNotExist as e:
        logger.error(e)
        pass
    except Exception as e:
        logger.error(e)
        pass
