"""Views."""

import datetime

from memberaudit.models import Character

from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import redirect, render
from django.utils import timezone

from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag
from .utils import remove_character_from_acl, add_character_to_acl

from whctools import __title__
from whctools.models import Acl, Applications, ACLHistory, AclHistoryRequest
from whctools.app_settings import (
    LARGE_REJECT,
    MEDIUM_REJECT,
    SHORT_REJECT,
    TRANSIENT_REJECT,
)

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


@login_required
@permission_required("whctools.basic_access")
def index(request):
    """Render index view."""
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
    
    existing_acls = Acl.objects.all()

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
        "existing_acls": existing_acls,
        "reject_timers": {
            "large_reject": LARGE_REJECT,
            "medium_reject": MEDIUM_REJECT,
            "short_reject": SHORT_REJECT,
            "transient_reject": TRANSIENT_REJECT,
        },
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
def withdraw(request, char_id, acl_name="WHC"):
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
        logger.debug(f"Removing {eve_char_applications.eve_character.character_name} from {acl_name}")
        remove_character_from_acl(eve_char_applications.eve_character.character_id, acl_name, Applications.MembershipStates.ACCEPTED, eve_char_applications.member_state, ACLHistory.ApplicationStateChangeReason.REMOVED )
        notify.info(
            request.user,
            "WHC application",
            f"You have left the WHC Community on {eve_char_applications.eve_character.character_name}.",
        )

    else:
        eve_char_applications.member_state = Applications.MembershipStates.REJECTED
        eve_char_applications.reject_reason = Applications.RejectionStates.WITHDRAWN
        eve_char_applications.reject_timeout = timezone.now() + datetime.timedelta(
            minutes=TRANSIENT_REJECT
        )
        notify.warning(
            request.user,
            "WHC application",
            f"You have withdrawn from the WHC Community on {eve_char_applications.eve_character.character_name}. You will now be subject to a short timer before you can reapply.",
        )

    eve_char_applications.save()

    return redirect("/whctools")


@login_required
@permission_required("whctools.whc_officer")
def accept(request, char_id, acl_name=""):

    whcapplication = Applications.objects.filter(
        eve_character_id=char_id
    ).select_related("eve_character")


    if whcapplication:
        member_application = whcapplication[0]
        old_state = member_application.member_state
        member_application.member_state = Applications.MembershipStates.ACCEPTED
        member_application.save()
        main_user = member_application.eve_character.character_ownership.user
        add_character_to_acl(acl_name, member_application.eve_character, old_state, Applications.MembershipStates.ACCEPTED, ACLHistory.ApplicationStateChangeReason.ACCEPTED)

        notify.success(
            main_user,
            "WHC application",
            f"Your application to the WHC Community on {member_application.eve_character.character_name} has been approved.",
        )

    return redirect("/whctools/staff")




# @@@ TODO - Add to the views.html templates the ability to remove from specific acls
@login_required
@permission_required("whctools.whc_officer")
def reject(request, char_id, reason, days, acl_name="WHC"):

    whcapplication = Applications.objects.filter(eve_character_id=char_id)

    if whcapplication:  # @@@ move this into template
        old_state = whcapplication[0].member_state
        whcapplication[0].member_state = Applications.MembershipStates.REJECTED
        if reason == "skills":
            whcapplication[0].reject_reason = Applications.RejectionStates.SKILLS
        elif reason == "removed":
            logger.debug(f"Removing {whcapplication[0].eve_character.character_name} from {acl_name}")
            whcapplication[0].reject_reason = Applications.RejectionStates.REMOVED

            remove_character_from_acl(whcapplication[0].eve_character.character_id, acl_name, old_state, whcapplication[0].member_state, ACLHistory.ApplicationStateChangeReason.REMOVED )


        else:
            whcapplication[0].reject_reason = Applications.RejectionStates.OTHER
            logger.debug(f"Removing {whcapplication[0].eve_character.character_name} from {acl_name}")
            remove_character_from_acl(whcapplication[0].eve_character.character_id, acl_name, old_state, whcapplication[0].member_state, ACLHistory.ApplicationStateChangeReason.REMOVED )
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
def reset(request, char_id, acl_name="WHC"):

    whcapplication = Applications.objects.filter(eve_character_id=char_id)

    if whcapplication:
        old_state = whcapplication[0].member_state
        whcapplication[0].member_state = Applications.MembershipStates.NOTAMEMBER
        whcapplication[0].save()
        main_user = whcapplication[0].eve_character.character_ownership.user
        
        if old_state == Applications.MembershipStates.ACCEPTED:
            logger.debug(f"Removing {whcapplication[0].eve_character.character_name} from {acl_name}")
            remove_character_from_acl(whcapplication[0].eve_character.character_id, acl_name, old_state, whcapplication[0].member_state, ACLHistory.ApplicationStateChangeReason.REMOVED )

        notify.success(
            main_user,
            "WHC application",
            f"Your application to the WHC Community on {whcapplication[0].eve_character.character_name} has been reset.\nYou may now reapply if you wish!",
        )

    return redirect("/whctools/staff")


@login_required
@permission_required("whctools.whc_officer")
def list_acl_members(request, acl_pk=""):

    acl_obj = Acl.objects.get(pk=acl_pk)
    if not acl_obj:
        return redirect("/whctools")
    members_on_acl = acl_obj.characters.all()
    date_selected = None
    parsed_acl_history = []

    if request.method == 'POST':
        logger.debug("POST request for acl history")
        form = AclHistoryRequest(request.POST)
        if form.is_valid():
            
            date_selected = form.cleaned_data.get("date_of_change")
            acl_history_entries = ACLHistory.objects.filter(date_of_change__gte=date_selected)
            logger.debug(f"Pulling ACL history after {date_selected} for {acl_pk}")
            parsed_acl_history = {}
            last_known_change = None
            for entry in acl_history_entries:
                if last_known_change is None or entry.date_of_change > last_known_change:
                    new_state = Applications.MembershipStates(entry.new_state)
                    if new_state in [Applications.MembershipStates.NOTAMEMBER, Applications.MembershipStates.APPLIED, Applications.MembershipStates.REJECTED]:
                        action = "Remove"
                    else:
                        action = "Add"
                    last_known_change = entry.date_of_change
                    parsed_acl_history[entry.character.character_name]  = {
                        "date": entry.date_of_change,
                        "portrait_url": entry.character.portrait_url(32),
                        "name": entry.character.character_name,
                        "state":new_state.name,
                        "action": action,
                        "reason": entry.get_reason_for_change_display()
                    }
            
            parsed_acl_history = list(parsed_acl_history.values())


    context = {
        "members": sorted([{
            "name": m.character_name,
            "corp": m.corporation_name,
            "alliance": m.alliance_name,
            "portrait_url": m.portrait_url(32),
        } for m in members_on_acl], key=lambda x: x["name"]), 
        "acl_name": acl_pk,
        "date_selected": date_selected,
        "acl_changes": parsed_acl_history,
        "acl_history_request": AclHistoryRequest()
        }

    return render(request, "whctools/list_acl_members.html", context)



