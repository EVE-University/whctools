"""Views."""

import datetime

from memberaudit.models import Character

from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import redirect, render
from django.utils import timezone

from allianceauth.eveonline.models import EveCharacter
from allianceauth.framework.api.user import get_main_character_from_eve_character
from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from whctools import __title__
from whctools.models import Acls, Applications, KnownAclAccess

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


@login_required
@permission_required("whctools.basic_access")
def index(request):
    """Render index view."""
    logger.debug(request.user)
    owned_chars_query = (
        EveCharacter.objects.filter(character_ownership__user=request.user)
        .select_related("memberaudit_character", "applications")
        .order_by("character_name")
    )
    auth_characters = []
    unregistered_chars = []
    now = timezone.now()
    for eve_char in owned_chars_query:
        try:
            eve_char.applications
        except AttributeError:
            logger.debug(AttributeError)
            Applications.objects.update_or_create(eve_character=eve_char)

        try:
            macharacter: Character = eve_char.memberaudit_character
            application: Applications = eve_char.applications
        except AttributeError:
            unregistered_chars.append(
                {
                    "char_name": eve_char.character_name,
                    "portrait_url": eve_char.portrait_url(64),
                }
            )
        else:
            reject_timeout = application.reject_timeout - now
            timedout = reject_timeout.total_seconds() < 0
            if (
                timedout
                and application.member_state == Applications.MembershipStates.REJECTED
            ):
                application.member_state = Applications.MembershipStates.NOTAMEMBER
                application.reject_reason = Applications.RejectionStates.NONE
                application.save()

            auth_characters.append(
                {
                    "application": application,
                    "char_name": eve_char.character_name,
                    "char_id": eve_char.character_id,
                    "portrait_url": eve_char.portrait_url(64),
                    "character": macharacter,
                    "is_shared": macharacter.is_shared,
                }
            )

    try:
        main_character_id = request.user.profile.main_character.character_id
    except AttributeError:
        main_character_id = None

    context = {
        "is_officer": request.user.has_perm("whctools.whc_officer"),
        "auth_characters": auth_characters,
        "unregistered_chars": unregistered_chars,
        "main_character_id": main_character_id,
    }

    return render(request, "whctools/index.html", context)


@login_required
@permission_required("whctools.whc_officer")
def staff(request):
    """Render staff view."""

    chars_applied = (
        Applications.objects.filter(member_state=Applications.MembershipStates.APPLIED)
        .select_related("eve_character__memberaudit_character")
        .order_by("last_updated")
    )
    chars_rejected = (
        Applications.objects.filter(member_state=Applications.MembershipStates.REJECTED)
        .select_related("eve_character__memberaudit_character")
        .order_by("last_updated")
        .reverse()
    )
    chars_accepted = (
        Applications.objects.filter(member_state=Applications.MembershipStates.ACCEPTED)
        .select_related("eve_character__memberaudit_character")
        .order_by("eve_character__character_name")
    )

    context = {
        "accepted_chars": chars_accepted,
        "rejected_chars": chars_rejected,
        "applied_chars": chars_applied,
    }
    return render(request, "whctools/staff.html", context)


@login_required
@permission_required("whctools.basic_access")
def apply(request, char_id):
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
        return redirect("/whctools")

    eve_char_applications = owned_chars_query[0].applications

    # Check if not already a member
    if eve_char_applications.member_state == Applications.MembershipStates.ACCEPTED:
        return redirect("/whctools")

    # Check if rejected
    if eve_char_applications.member_state == Applications.MembershipStates.REJECTED:
        return redirect("/whctools")

    eve_char_applications.member_state = Applications.MembershipStates.APPLIED
    eve_char_applications.save()

    notify.info(
        request.user,
        "WHC application",
        f"You have applied to the WHC Community on {owned_chars_query[0].character_name}.",
    )

    return redirect("/whctools")


@login_required
@permission_required("whctools.basic_access")
def withdraw(request, char_id):
    """Remove Application"""
    owned_chars_query = (
        EveCharacter.objects.filter(
            character_ownership__user=request.user, character_id=char_id
        )
        .select_related("applications")
        .order_by("character_name")
    )

    if not owned_chars_query:
        logger.debug("No Match!")
        return redirect("/whctools")

    eve_char_applications = owned_chars_query[0].applications

    if eve_char_applications.member_state == Applications.MembershipStates.ACCEPTED:
        # Dont apply penalty to leaving members
        eve_char_applications.member_state = Applications.MembershipStates.NOTAMEMBER
        notify.info(
            request.user,
            "WHC application",
            f"You have left the WHC Community on {owned_chars_query[0].character_name}.",
        )

    else:
        eve_char_applications.member_state = Applications.MembershipStates.REJECTED
        eve_char_applications.reject_reason = Applications.RejectionStates.WITHDRAWN
        eve_char_applications.reject_timeout = timezone.now() + datetime.timedelta(
            minutes=2
        )  # @@@ Make this into a variable
        notify.warning(
            request.user,
            "WHC application",
            f"You have withdrawn from the WHC Community on {owned_chars_query[0].character_name}. You will now be subject to a short timer before you can reapply.",
        )

    eve_char_applications.save()

    return redirect("/whctools")


@login_required
@permission_required("whctools.whc_officer")
def accept(request, char_id):

    whcapplication = Applications.objects.filter(
        eve_character_id=char_id
    ).select_related("eve_character")

    if whcapplication:
        whcapplication[0].member_state = Applications.MembershipStates.ACCEPTED
        whcapplication[0].save()
        main_user = whcapplication[0].eve_character.character_ownership.user
        notify.success(
            main_user,
            "WHC application",
            f"Your application to the WHC Community on {whcapplication[0].eve_character.character_name} has been approved.",
        )

    return redirect("/whctools/staff")


@login_required
@permission_required("whctools.whc_officer")
def reject(request, char_id, reason, days):

    whcapplication = Applications.objects.filter(eve_character_id=char_id)

    if whcapplication:  # @@@ move this into template
        whcapplication[0].member_state = Applications.MembershipStates.REJECTED
        if reason == "skills":
            whcapplication[0].reject_reason = Applications.RejectionStates.SKILLS
        elif reason == "removed":
            whcapplication[0].reject_reason = Applications.RejectionStates.REMOVED
        else:
            whcapplication[0].reject_reason = Applications.RejectionStates.OTHER
        whcapplication[0].reject_timeout = timezone.now() + datetime.timedelta(
            days=int(days)
        )
        whcapplication[0].save()
        main_user = whcapplication[0].eve_character.character_ownership.user
        notify.danger(
            main_user,
            "WHC application",
            f"Your application to the WHC Community on {whcapplication[0].eve_character.character_name} has been rejected.\nReason: {whcapplication[0].get_reject_reason_display()}",
        )

    return redirect("/whctools/staff")


@login_required
@permission_required("whctools.whc_officer")
def reset(request, char_id):

    whcapplication = Applications.objects.filter(eve_character_id=char_id)

    if whcapplication:
        whcapplication[0].member_state = Applications.MembershipStates.NOTAMEMBER
        whcapplication[0].save()
        main_user = whcapplication[0].eve_character.character_ownership.user
        notify.success(
            main_user,
            "WHC application",
            f"Your application to the WHC Community on {whcapplication[0].eve_character.character_name} has been reset.\nYou may now reapply if you wish!",
        )

    return redirect("/whctools/staff")


@login_required
@permission_required("whctools.whc_officer")
def get_current_acl_truth(request, acl_name="whc"):

    acl_obj = Acls.object.get(primary_key=acl_name)
    members_on_acl = KnownAclAccess.object.filter(acls=acl_obj)

    output = {}
    for member in members_on_acl:
        main = get_main_character_from_eve_character(member.eve_character.name)
        alts_with_acl_access = output.setdefault(main, {})
        if member.eve_character.name != main.name:
            alts_with_acl_access["main"] = main
        else:
            alts_with_acl_access.setdefault("alts", []).append(member.eve_character)

    context = {"members": output, "acl_name": acl_name}

    return render(request, "whctools/list_acl_members.html", context)
