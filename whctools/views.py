"""Views."""

from memberaudit.models import Character

from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from whctools.views_actions.player_actions import withdraw_app
from whctools.views_staff.open_applications import getSkills

try:
    # Alliance auth 4.0 only
    from allianceauth.framework.api.evecharacter import (
        get_main_character_from_evecharacter,
        get_user_from_evecharacter,
    )
    from allianceauth.framework.api.user import (
        get_all_characters_from_user,
        get_main_character_name_from_user,
    )
except Exception:
    # Alliance 3.0 backwards compatibility
    from .aa3compat import (
        bc_get_main_character_from_evecharacter as get_main_character_from_evecharacter,
    )
    from .aa3compat import bc_get_user_from_eve_character as get_user_from_evecharacter
    from .aa3compat import (
        bc_get_all_characters_from_user as get_all_characters_from_user,
    )
    from .aa3compat import (
        bc_get_main_character_name_from_user as get_main_character_name_from_user,
    )

from whctools import __title__
from whctools.app_settings import (
    LARGE_REJECT,
    MEDIUM_REJECT,
    SHORT_REJECT,
    TRANSIENT_REJECT,
)
from whctools.models import Acl, ACLHistory, AclHistoryRequest, Applications

from .utils import (
    add_character_to_acl,
    generate_raw_copy_for_acl,
    get_corp_requirements_message,
    is_character_in_allowed_corp,
    log_application_change,
    remove_all_alts,
    remove_character_from_acl,
    remove_character_from_community,
)
from .views_actions.player_actions import submit_application
from .views_staff.open_applications import all_characters_currently_with_open_apps
from .views_staff.rejected_applications import get_rejected_apps
from .views_staff.staff_utils import build_default_staff_context

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
    main_character_name = get_main_character_name_from_user(request.user)

    try:
        main_character_id = request.user.profile.main_character.character_id
    except AttributeError:
        main_character_id = None

    is_main_accepted = False
    for eve_char in owned_chars_query:

        if eve_char.character_name == main_character_name:
            try:
                is_main_accepted = (
                    eve_char.applications.member_state
                    == Applications.MembershipStates.ACCEPTED
                )

                logger.debug(
                    f"main character found: {main_character_name}, app status is {eve_char.applications.get_member_state_display()}, so is_main_accepted is {is_main_accepted}"
                )
                break
            except Exception:
                logger.debug("No app status on main")
                pass

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
            is_in_approved_corp = is_character_in_allowed_corp(eve_char)
            corp_requirements_message = get_corp_requirements_message()
            logger.debug(
                f"Character {eve_char.character_name} is in approved corp: {is_in_approved_corp}"
            )
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
                    "corporation_name": eve_char.corporation_name,
                    "alliance_name": eve_char.alliance_name,
                    "char_id": eve_char.character_id,
                    "portrait_url": eve_char.portrait_url(64),
                    "character": macharacter,
                    "is_shared": macharacter.is_shared,
                    "is_main": main_character_id == eve_char.character_id,
                    "is_main_member": is_main_accepted,
                    "is_in_approved_corp": is_in_approved_corp,
                }
            )

    context = {
        "is_officer": request.user.has_perm("whctools.whc_officer"),
        "auth_characters": auth_characters,
        "unregistered_chars": unregistered_chars,
        "main_character_id": main_character_id,
        "corp_requirements_message": corp_requirements_message,
    }

    return render(request, "whctools/index.html", context)


@login_required
@permission_required("whctools.whc_officer")
def open_applications(request):
    context = build_default_staff_context("Open Apps")
    context["existing_acls"] = Acl.objects.all()
    context["applied_chars"] = all_characters_currently_with_open_apps()
    return render(request, "whctools/staff/staff_apps_in_progress.html", context)


@login_required
@permission_required("whctools.whc_officer")
def rejected_applications(request):
    context = build_default_staff_context("Rejected Apps")
    context["rejected_chars"] = get_rejected_apps()
    return render(request, "whctools/staff/staff_rejected_apps.html", context)


@login_required
@permission_required("whctools.whc_officer")
def list_acls(request):
    context = build_default_staff_context("ACL Lists")
    context["existing_acls"] = Acl.objects.all()
    return render(request, "whctools/staff/staff_list_acls.html", context)


@login_required
@permission_required("whctools.basic_access")
def apply(request, char_id):

    _ = submit_application(request, char_id)  # returns a message, TODO use it!

    return redirect("/whctools")


@login_required
@permission_required("whctools.basic_access")
def withdraw(request, char_id, acl_name="WHC"):
    """Remove Application"""
    withdraw_app(request, char_id, acl_name)

    return redirect("/whctools")


@login_required
@permission_required("whctools.whc_officer")
def accept(request, char_id, acl_name="WHC"):

    whcapplication = Applications.objects.filter(
        eve_character_id=char_id
    ).select_related("eve_character")

    if whcapplication:
        member_application = whcapplication[0]
        old_state = member_application.member_state
        member_application.member_state = Applications.MembershipStates.ACCEPTED
        member_application.save()
        main_user = member_application.eve_character.character_ownership.user

        log_application_change(
            application=member_application,
            old_state=member_application.member_state,
        )
        add_character_to_acl(
            acl_name,
            member_application.eve_character,
            old_state,
            Applications.MembershipStates.ACCEPTED,
            ACLHistory.ApplicationStateChangeReason.ACCEPTED,
        )

        notify.success(
            main_user,
            f"{acl_name} application: Approved",
            f"Your application to the {acl_name} Community on {member_application.eve_character.character_name} has been approved.",
        )

    return redirect("/whctools/staff/open")


# @@@ TODO - Add to the views.html templates the ability to remove from specific acls
@login_required
@permission_required("whctools.whc_officer")
def reject(request, char_id, reason, days, source="staff", acl_name="WHC"):

    logger.debug(f"char_id: {char_id}, reason {reason}, days {days}")
    whcapplication = Applications.objects.filter(eve_character_id=char_id)

    logger.debug(whcapplication)

    if whcapplication:  # @@@ move this into template
        member_application = whcapplication[0]
        old_state = member_application.member_state
        notify_subject = "Application Denied"

        # Removed should only be triggered by the removal by staff directly after a membership is allready accepted
        if reason == "removed":
            # If a WHC character is forcefully removed, remove all alts as well.
            logger.debug(
                f"Removing {member_application.eve_character.character_name} and all their alts from {acl_name}"
            )
            rejection_reason = Applications.RejectionStates.REMOVED
            notify_subject = "Membership Revoked"
            notification_names = remove_all_alts(
                acl_name,
                member_application,
                Applications.MembershipStates.REJECTED,
                rejection_reason,
                days,
            )

        else:
            # Other can be used for individual removal of alts that need cleaning up.
            # note: currently only used on the reject an open application - additional @@@ TODO to hook up to the remove membership page
            logger.debug(
                f"Singleton removal of {member_application.eve_character.character_name}"
            )

            rejection_reason = (
                Applications.RejectionStates.SKILLS
                if reason == "skills"
                else Applications.RejectionStates.OTHER
            )
            notification_names = member_application.eve_character.character_name
            remove_character_from_community(
                member_application,
                Applications.MembershipStates.REJECTED,
                rejection_reason,
                days,
            )
            remove_character_from_acl(
                member_application.eve_character.character_id,
                acl_name,
                old_state,
                member_application.member_state,
                rejection_reason,
            )

        log_application_change(
            application=member_application, old_state=old_state, reason=rejection_reason
        )

        notify.danger(
            member_application.eve_character.character_ownership.user,
            f"{acl_name} Community: {notify_subject}",
            f"Your application to the {acl_name} Community on {notification_names} has been rejected.\n\n\t* Reason: {member_application.get_reject_reason_display()}"
            + "\n\nIf you have any questions about this action, please contact WHC Community Coordinators on discord.",
        )
    if source == "acl":
        return redirect(f"/whctools/staff/action/{acl_name}/view")
    else:
        return redirect("/whctools/staff/open")


@login_required
@permission_required("whctools.whc_officer")
def reset(request, char_id, acl_name="WHC"):

    whcapplication = Applications.objects.filter(eve_character_id=char_id)

    if whcapplication:
        member_application = whcapplication[0]
        old_state = member_application.member_state
        member_application.member_state = Applications.MembershipStates.NOTAMEMBER
        member_application.save()
        log_application_change(
            application=member_application,
            old_state=old_state,
            reason=Applications.RejectionStates.OTHER,
        )

        if old_state == Applications.MembershipStates.ACCEPTED:
            logger.debug(
                f"Removing {member_application.eve_character.character_name} from {acl_name}"
            )
            remove_character_from_acl(
                member_application.eve_character.character_id,
                acl_name,
                old_state,
                member_application.member_state,
                ACLHistory.ApplicationStateChangeReason.REMOVED,
            )

        notify.success(
            member_application.eve_character.character_ownership.user,
            f"{acl_name} application availability reset",
            f"Your application to the {acl_name} Community on {member_application.eve_character.character_name} has been reset.\nYou may now reapply if you wish!",
        )

    return redirect("/whctools/staff/rejected")


@login_required
@permission_required("whctools.whc_officer")
def list_acl_members(request, acl_pk=""):

    acl_obj = Acl.objects.get(pk=acl_pk)
    if not acl_obj:
        return redirect("/whctools")
    members_on_acl = acl_obj.characters.all()
    date_selected = None
    parsed_acl_history = []

    if request.method == "POST":
        logger.debug("POST request for acl history")
        form = AclHistoryRequest(request.POST)
        if form.is_valid():

            date_selected = form.cleaned_data.get("date_of_change")
            acl_history_entries = ACLHistory.objects.filter(
                date_of_change__gte=date_selected
            )
            logger.debug(f"Pulling ACL history after {date_selected} for {acl_pk}")
            parsed_acl_history = {}
            last_known_change = None
            for entry in acl_history_entries:
                if (
                    last_known_change is None
                    or entry.date_of_change > last_known_change
                ):
                    new_state = Applications.MembershipStates(entry.new_state)
                    if new_state in [
                        Applications.MembershipStates.NOTAMEMBER,
                        Applications.MembershipStates.APPLIED,
                        Applications.MembershipStates.REJECTED,
                    ]:
                        action = "Remove"
                    else:
                        action = "Add"
                    last_known_change = entry.date_of_change
                    parsed_acl_history[entry.character.character_name] = {
                        "date": entry.date_of_change,
                        "portrait_url": entry.character.portrait_url(32),
                        "name": entry.character.character_name,
                        "state": new_state.name,
                        "action": action,
                        "reason": entry.get_reason_for_change_display(),
                    }

            parsed_acl_history = list(parsed_acl_history.values())

    mains_and_alts = {}
    for memb in members_on_acl:
        user_obj = get_user_from_evecharacter(memb)

        mains_and_alts.setdefault(user_obj.id, {})
        if "main" not in mains_and_alts[user_obj.id].keys():
            mains_and_alts[user_obj.id]["main"] = get_main_character_from_evecharacter(
                memb
            )

        if mains_and_alts[user_obj.id]["main"] is None:
            "string"["error"]

        mains_and_alts[user_obj.id].setdefault("alts", []).append(memb)
        mains_and_alts[user_obj.id].setdefault(
            "complete_alts", get_all_characters_from_user(user_obj)
        )

    # note to self - x[1] is not a list index, but a tuple index, becaus its .items(), returning (key, value)
    # and it has to be for it to remain a dict after sorting
    alphabetical_mains = dict(
        sorted(mains_and_alts.items(), key=lambda x: x[1]["main"].character_name)
    )

    for character in alphabetical_mains.values():
        character["main"] = {
            "name": character["main"].character_name,
            "corp": character["main"].corporation_name,
            "alliance": character["main"].alliance_name,
            "portrait_url": character["main"].portrait_url(32),
            "character_id": character["main"].id,
        }
        character["alts"] = list(
            sorted(
                [
                    {
                        "name": m.character_name,
                        "corp": m.corporation_name,
                        "alliance": m.alliance_name,
                        "portrait_url": m.portrait_url(32),
                        "character_id": m.id,
                    }
                    for m in character["alts"]
                    if m.character_name != character["main"]["name"]
                ],
                key=lambda x: x["name"],
            )
        )

        acl_alt_names = [alt["name"] for alt in character["alts"]]

        character["complete_alts"] = list(
            sorted(
                [
                    {
                        "name": m.character_name,
                        "corp": m.corporation_name,
                        "alliance": m.alliance_name,
                        "portrait_url": m.portrait_url(32),
                    }
                    for m in character["complete_alts"]
                    if m.character_name not in acl_alt_names
                    and m.character_name != character["main"]["name"]
                ],
                key=lambda x: x["name"],
            )
        )

    context = {
        "members": alphabetical_mains.values(),
        "acl_name": acl_pk,
        "date_selected": date_selected,
        "acl_changes": parsed_acl_history,
        "raw_acl_copy_text": generate_raw_copy_for_acl(alphabetical_mains),
        "acl_history_request": AclHistoryRequest(),
        "reject_timers": {
            "large_reject": LARGE_REJECT,
            "medium_reject": MEDIUM_REJECT,
            "short_reject": SHORT_REJECT,
            "transient_reject": TRANSIENT_REJECT,
        },
    }

    return render(request, "whctools/list_acl_members.html", context)


@login_required
@permission_required("whctools.whc_officer")
def get_skills(request, char_id):
    logger.debug(f"Get Skills for {char_id}")
    skill_sets = getSkills(char_id)

    return JsonResponse(skill_sets)
