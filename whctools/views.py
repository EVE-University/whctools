"""Views."""

import json
from datetime import timedelta

from memberaudit.models import Character

from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from esi.decorators import token_required

from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from whctools.views_actions.player_actions import withdraw_app
from whctools.views_staff.open_applications import getMail, getSkills, updateMail

try:
    # Alliance auth 4.0 only
    from allianceauth.framework.api.evecharacter import (
        get_main_character_from_evecharacter,
    )
    from allianceauth.framework.api.user import get_main_character_name_from_user
except Exception:
    # Alliance 3.0 backwards compatibility
    from .aa3compat import (
        bc_get_main_character_from_evecharacter as get_main_character_from_evecharacter,
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
    add_character,
    generate_raw_copy_for_acl,
    get_corp_requirements_message,
    is_character_in_allowed_corp,
    log_application_change,
    remove_all_alts,
    remove_character,
    remove_character_from_community,
    sync_groups_with_acl_helper,
    sync_wanderer_with_acl_helper,
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
        "corp_requirements_message": get_corp_requirements_message(),
        "withdraw_timeout": TRANSIENT_REJECT,
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


# @login_required
# @permission_required("whctools.whc_officer")
# def list_acls(request):
#    context = build_default_staff_context("ACL Lists")
#    context["existing_acls"] = Acl.objects.all()
#    return render(request, "whctools/staff/staff_list_acls.html", context)


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
@token_required(scopes="esi-mail.send_mail.v1")
def accept(request, token, char_id, acl_name="WHC"):

    whcapplication = Applications.objects.filter(
        eve_character__character_id=char_id
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
        add_character(
            acl_name,
            member_application.eve_character,
            old_state,
            Applications.MembershipStates.ACCEPTED,
            ACLHistory.ApplicationStateChangeReason.ACCEPTED,
            request.user,
            token,
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
    logger.debug(
        f"Attempting to delete character with char_id: {char_id}, reason: {reason}, days: {days}"
    )

    if source == "acl":
        redirect_target = redirect(f"/whctools/staff/action/{acl_name}/view")
    else:
        redirect_target = redirect("/whctools/staff/open")

    whcapplication = Applications.objects.filter(eve_character__character_id=char_id)

    if not whcapplication.exists():
        logger.error(f"Cannot find character {char_id} to delete.")
        return redirect_target

    # @@@ move this into template?
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
            f"Removing {member_application.eve_character.character_name} from {acl_name}"
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
        remove_character(
            acl_name,
            member_application.eve_character,
            old_state,
            member_application.member_state,
            rejection_reason,
        )

    log_application_change(
        application=member_application, old_state=old_state, reason=rejection_reason
    )

    try:
        notify.danger(
            member_application.eve_character.character_ownership.user,
            f"{acl_name} Community: {notify_subject}",
            f"Your application to the {acl_name} Community on {notification_names} has been rejected.\n\n\t* Reason: {member_application.get_reject_reason_display()}"
            + "\n\nIf you have any questions about this action, please contact WHC Community Coordinators on discord.",
        )
    except Exception:  # Best effort. If the owner doesn't exist, forget it.
        pass

    return redirect_target


@login_required
@permission_required("whctools.whc_officer")
def reset(request, char_id, acl_name="WHC"):

    whcapplication = Applications.objects.filter(eve_character__character_id=char_id)

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
            remove_character(
                acl_name,
                member_application.eve_character.character_id,
                old_state,
                member_application.member_state,
                ACLHistory.ApplicationStateChangeReason.REMOVED,
            )

        try:
            notify.success(
                member_application.eve_character.character_ownership.user,
                f"{acl_name} application availability reset",
                f"Your application to the {acl_name} Community on {member_application.eve_character.character_name} has been reset.\nYou may now reapply if you wish!",
            )
        except Exception:  # Best effort. If the owner doesn't exist, forget it.
            pass

    return redirect("/whctools/staff/rejected")


@login_required
@permission_required("whctools.whc_officer")
def list_acl_members(request, acl_pk=""):
    acl_obj = Acl.objects.get(pk=acl_pk)
    if not acl_obj:
        return redirect("/whctools")
    members_on_acl = acl_obj.characters.all()
    date_selected = None

    # Audit Log
    acl_history_request = AclHistoryRequest(
        initial={"date_of_change": timezone.now() - timedelta(days=7), "limit": 0}
    )
    acl_changes = []
    num_acl_changes = 0
    if request.method == "POST":
        logger.debug("POST request for acl history")
        form = AclHistoryRequest(request.POST)
        logger.debug(form)
        if form.is_valid():
            acl_history_request = form  # Preserve previous query

            date_selected = form.cleaned_data.get("date_of_change")
            acl_history_entries = ACLHistory.objects.filter(
                date_of_change__gte=date_selected
            ).order_by("date_of_change")
            character_name = form.cleaned_data.get("character_name")
            if character_name != "":
                acl_history_entries = acl_history_entries.filter(
                    character__character_name=character_name
                )
            limit = form.cleaned_data.get("limit")
            if limit != 0:
                acl_history_entries = acl_history_entries[:limit]
            logger.debug(
                f"Pulling {'all' if limit==0 else str(limit)} ACL history entries after {date_selected} for {acl_pk}"
            )
            for entry in acl_history_entries:
                acl_changes.append(
                    {
                        "member": entry.character.character_name,
                        "date": entry.date_of_change,
                        "name": entry.character.character_name,
                        "old_state": Applications.MembershipStates(
                            entry.old_state
                        ).name,
                        "new_state": Applications.MembershipStates(
                            entry.new_state
                        ).name,
                        "reason": entry.get_reason_for_change_display(),
                    }
                )
            acl_changes = sorted(acl_changes, key=lambda _: _["date"])
            num_acl_changes = len(acl_changes)

    # ACL
    char_list = []
    mains_set = set([])  # just mains in ACL
    players_set = set([])  # includes mains in and not in ACL
    for member in members_on_acl:
        name = member.character_name
        char_id = member.character_id
        main = None
        corp = member.corporation_name
        alliance = member.alliance_name
        error = None

        main_character = get_main_character_from_evecharacter(member)
        if main_character is None:
            main = "?"
            error = "Orphaned character"
            logger.info(
                f"WHC ACL '{acl_pk}': character '{name}' is an orphan with no main"
            )
        else:
            main = main_character.character_name
            players_set.add(main)

        if name == main:
            mains_set.add(main)

        if not is_character_in_allowed_corp(member):
            logger.info(
                f"WHC ACL '{acl_pk}': character '{name}' is in an invalid corp or alliance"
            )
            error = "Disallowed corp/alliance"
        # I believe this isn't possible, since a user has to swap Uni mains in
        # order for them to remain in the Uni.
        if main_character is not None and not is_character_in_allowed_corp(
            main_character
        ):
            logger.info(
                f"WHC ACL '{acl_pk}': character '{name}' has a main '{main}' in an invalid corp or alliance"
            )
            error = "Main in disallowed corp/alliance"

        char_list.append(
            {
                "name": name,
                "char_id": char_id,
                "main": main,
                "corp": corp,
                "alliance": alliance,
                "error": error,
                "is_main": (name == main),
                "main_in_acl": False,  # We'll backfill this
            }
        )

    # Backfill mains
    for char in char_list:
        if char["main"] in mains_set:
            char["main_in_acl"] = True

    # sorted() Key function
    class ACLSorter(object):
        __slots__ = ["obj"]

        def __init__(self, obj):
            self.obj = obj

        def __getitem__(self, key):
            return self.obj[key]

        def __lt__(self, rhs):
            lhs = self.obj
            # Always float errors to the top
            # If they're both errors, revert to normal behavior
            if lhs["error"] is not None and rhs["error"] is None:
                return True
            if rhs["error"] is not None and lhs["error"] is None:
                return False
            # Sort by main first
            if lhs["main"] != rhs["main"]:
                return lhs["main"] < rhs["main"]
            else:  # both are alts of the same main
                # Then float the main to the top of the alt group
                if lhs["name"] == lhs["main"]:
                    return True
                if rhs["name"] == rhs["main"]:
                    return False
                return lhs["name"] < rhs["name"]

        def __gt__(self, rhs):
            return not self.__lt__(rhs)

        def __eq__(self, rhs):
            return False

        def __le__(self, rhs):
            return self.__lt__(rhs)

        def __ge__(self, rhs):
            return self.__gt__(rhs)

        __hash__ = None

    sorted_char_list = sorted(char_list, key=ACLSorter)
    total_mains = len(mains_set)
    total_players = len(players_set)
    total_chars = len(char_list)

    context = {
        "acl_name": acl_pk,
        "total_mains": total_mains,
        "total_chars": total_chars,
        "total_players": total_players,
        "characters": sorted_char_list,
        "date_selected": date_selected,
        "acl_changes": acl_changes,
        "num_acl_changes": num_acl_changes,
        "raw_acl_copy_text": generate_raw_copy_for_acl(sorted_char_list),
        "acl_history_request": acl_history_request,
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


@login_required
@permission_required("whctools.whc_officer")
def sync_groups_with_acl(request, acl_pk="WHC"):
    sync_groups_with_acl_helper(acl_pk)
    return redirect(f"/whctools/staff/action/{acl_pk}/view")


@login_required
@permission_required("whctools.whc_officer")
def sync_wanderer_with_acl(request, acl_pk="WHC"):
    sync_wanderer_with_acl_helper(acl_pk)
    return redirect(f"/whctools/staff/action/{acl_pk}/view")


@login_required
@permission_required("whctools.whc_officer")
def get_mail(request):
    mail = getMail()
    return JsonResponse(mail)


@login_required
@permission_required("whctools.whc_officer")
def update_mail(request):
    data = json.loads(request.body.decode("utf-8"))
    mail = data.get("mail")
    mail = updateMail(mail)
    return JsonResponse(mail)
