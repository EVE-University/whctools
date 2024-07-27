from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from whctools import __title__

from ..app_settings import TRANSIENT_REJECT
from ..models import ACLHistory, Applications
from ..utils import (
    force_update_memberaudit,
    is_character_in_allowed_corp,
    log_application_change,
    remove_character_from_acl,
    remove_character_from_community,
)

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


def submit_application(request, char_id):
    """Add Application"""
    owned_chars_query = (
        EveCharacter.objects.filter(
            character_ownership__user=request.user, character_id=char_id
        )
        .select_related("applications")
        .order_by("character_name")
    )

    if not owned_chars_query:
        logger.debug("No Match!")
        return "Something went wrong. Please contact @webservices on discord"

    eve_char_application = owned_chars_query[0].applications

    # Check if not already a member
    if eve_char_application.member_state == Applications.MembershipStates.ACCEPTED:
        return "This character is already a member! How'd you do this?"

    # Check if rejected
    if eve_char_application.member_state == Applications.MembershipStates.REJECTED:
        return "This character has been rejected previously and is still under cooldown for another application. Please contact WHC Community Coordinators on Discord"

    # Check if character is in a valid corp/alliance
    if not is_character_in_allowed_corp(eve_char_application.eve_character):
        logger.debug(f"Character {eve_char_application} applied but is in an invalid corp.")
        return "This character isn't in an approved corp/alliance."

    # If this is a new main application, queue up a forced memberaudit update
    main_eve_char = eve_char_application.get_main_character()
    if main_eve_char is None:
        return "This character has no Auth profile, which should not be possible. Please contact @webservices on discord."
    if eve_char_application == main_eve_char.applications:
        force_update_memberaudit(eve_char_application.eve_character)

    eve_char_application.member_state = Applications.MembershipStates.APPLIED
    eve_char_application.save()

    log_application_change(eve_char_application)

    notify.info(
        request.user,
        "WHC application: Application Submitted",  # @@@ todo, individual application to different communities
        f"You have applied to the WHC Community on {owned_chars_query[0].character_name}.",
    )

    return "Application Submitted"


def withdraw_app(request, char_id, acl_name):
    owned_chars_query = (
        EveCharacter.objects.filter(
            character_ownership__user=request.user, character_id=char_id
        )
        .select_related("applications")
        .order_by("character_name")
    )

    if not owned_chars_query:
        logger.debug("No Match!")
        return

    eve_char_application = owned_chars_query[0].applications

    if eve_char_application.member_state == Applications.MembershipStates.ACCEPTED:
        # Dont apply penalty to leaving members
        logger.debug(
            f"Removing {eve_char_application.eve_character.character_name} from {acl_name}"
        )
        old_state = eve_char_application.member_state
        reject_reason = Applications.RejectionStates.LEFT_COMMUNITY
        remove_character_from_community(
            eve_char_application,
            Applications.MembershipStates.REJECTED,
            reject_reason,
            reject_time=0,
        )
        remove_character_from_acl(
            eve_char_application.eve_character.character_id,
            acl_name,
            old_state,
            eve_char_application.member_state,
            ACLHistory.ApplicationStateChangeReason.LEFT_GROUP,
        )
        notify.info(
            request.user,
            f"{acl_name} Community: Left Community",
            f"You have left the {acl_name} Community on {eve_char_application.eve_character.character_name}.",
        )

    else:
        old_state = eve_char_application.member_state
        reject_reason = Applications.RejectionStates.WITHDRAWN
        remove_character_from_community(
            eve_char_application,
            Applications.MembershipStates.REJECTED,
            reject_reason,
            reject_time=TRANSIENT_REJECT,
        )

        notify.warning(
            request.user,
            f"{acl_name} application: Withdraw",
            f"You have withdrawn your open application for the {acl_name} Community on {eve_char_application.eve_character.character_name}. You will now be subject to a short timer before you can reapply.",
        )

    eve_char_application.save()
    log_application_change(
        eve_char_application, old_state=old_state, reason=reject_reason
    )
    return
