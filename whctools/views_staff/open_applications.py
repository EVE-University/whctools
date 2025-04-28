from memberaudit.models import Character

from allianceauth.eveonline.models import EveCharacter

from whctools.app_settings import ESI_TASK_TIMEOUT_SECONDS

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
from whctools.utils import (
    get_last_ma_update_time,
    get_welcome_mail,
    is_main_eve_character,
    update_welcome_mail,
)

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


def all_characters_currently_with_open_apps():

    chars_applied = (
        Applications.objects.filter(member_state=Applications.MembershipStates.APPLIED)
        .select_related("eve_character__memberaudit_character")
        .order_by("last_updated")
    )

    # When we pull skills from member audit, we want to be sure that
    # they are recent and valid. For main characters, we force an update
    # when that character applies. But if that pull fails (expired token,
    # etc.), we want to know that the skills are invalid. So we check
    # both the last skill update status as well as its age.
    #
    # Note that only the main character needs this. For alts, we allow
    # stale skill checks and rely on the 'Check Skills' panel in the UI.
    ma_is_valid = []
    is_main_char = []
    for app in chars_applied:
        try:
            eve_char = app.eve_character
        except Exception as e:
            logger.error(f"No character for {str(app)}: {e}")
            ma_is_valid.append(False)
            is_main_char.append(False)
            continue
        is_main = is_main_eve_character(eve_char)
        is_main_char.append(is_main)

        last_ma_update = get_last_ma_update_time(eve_char)  # returns 1970 if error
        app_applied_at = app.last_updated
        ma_age = (app_applied_at - last_ma_update).total_seconds()
        ma_is_valid.append(ma_age < ESI_TASK_TIMEOUT_SECONDS)

    return [
        {
            "application": application,
            "ma_is_valid": valid,
            "is_main_char": is_main,
        }
        for application, valid, is_main in zip(chars_applied, ma_is_valid, is_main_char)
    ]


def getSkills(eve_char_id):

    application = Applications.objects.filter(
        eve_character__character_id=eve_char_id
    ).select_related("eve_character")[0]

    existing_acls = Acl.objects.all()
    eve_char: EveCharacter = application.eve_character
    user = get_user_from_evecharacter(eve_char)
    all_characters = get_all_characters_from_user(user)

    alt_data = {}  # { alt : (last_updated, {skillset: can_fly}) }

    for char in all_characters:
        try:
            ma_character: Character = char.memberaudit_character
        except Exception as e:
            logger.error(
                f"Could not get MA Character for {char} belonging to {eve_char} - error: {e}"
            )
            continue
        else:
            last_update = get_last_ma_update_time(eve_char).strftime("%b %d, %Y")
            skillset_status = {}

            ma_character.update_skill_sets()
            for acl in existing_acls:
                for skillset in acl.skill_sets.all():
                    skillset_status[skillset.name] = (
                        ma_character.skill_set_checks.filter(skill_set=skillset)
                        .first()
                        .can_fly
                    )
            alt_data[char.character_name] = (last_update, skillset_status)

    return {
        "alt_data": alt_data,
        "applying_character": eve_char.character_name,
    }


def getMail():
    mail = get_welcome_mail()
    return {"mail": mail}


def updateMail(message):
    mail = update_welcome_mail(message)
    return {"mail": mail}
