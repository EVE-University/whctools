from memberaudit.models import Character

from allianceauth.eveonline.models import EveCharacter

try:
    # Alliance auth 4.0 only
    from allianceauth.framework.api.evecharacter import get_user_from_evecharacter
    from allianceauth.framework.api.user import get_all_characters_from_user
except Exception:
    # Alliance 3.0 backwards compatibility
    from ..aa3compat import bc_get_user_from_eve_character as get_user_from_evecharacter
    from ..aa3compat import (
        bc_get_all_characters_from_user as get_all_characters_from_user,
    )

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from whctools import __title__
from whctools.models import Acl, Applications

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


def all_characters_currently_with_open_apps():

    chars_applied = (
        Applications.objects.filter(member_state=Applications.MembershipStates.APPLIED)
        .select_related("eve_character__memberaudit_character")
        .order_by("last_updated")
    )

    return [{"application": application} for application in chars_applied]


def getSkills(eve_char_id):

    application = Applications.objects.filter(
        eve_character_id=eve_char_id
    ).select_related("eve_character")[0]

    existing_acls = Acl.objects.all()
    eve_char: EveCharacter = application.eve_character
    user = get_user_from_evecharacter(eve_char)
    all_characters = get_all_characters_from_user(user)

    characters_skillset_status = {}

    for char in all_characters:
        try:
            ma_character: Character = char.memberaudit_character
        except Exception as e:
            logger.error(
                f"Could not get MA Character for {char} belonging to {eve_char} - error: {e}"
            )
            continue
        else:
            ma_character.update_skill_sets()
            for acl in existing_acls:
                characters_skillset_status.setdefault(char.character_name, {})
                for skillset in acl.skill_sets.all():
                    characters_skillset_status[char.character_name][skillset.name] = (
                        ma_character.skill_set_checks.filter(skill_set=skillset)
                        .first()
                        .can_fly
                    )

    return {
        "skill_sets": characters_skillset_status,
        "applying_character": eve_char.character_name,
    }
