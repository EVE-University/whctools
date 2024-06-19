"""Views."""

from memberaudit.models import Character

from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import redirect, render
from django.utils import timezone

from allianceauth.eveonline.models import EveCharacter
from allianceauth.notifications import notify
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

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
    log_application_change,
    remove_all_alts,
    remove_character_from_acl,
    remove_character_from_community,
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
    main_character_name = get_main_character_name_from_user(request.user)

    try:
        main_character_id = request.user.profile.main_character.character_id
    except AttributeError:
        main_character_id = None

    main_app_status = Applications.MembershipStates.NOTAMEMBER
    for eve_char in owned_chars_query:
        if eve_char == main_character_name:
            try:
                main_app_status = eve_char.applications.member_state
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
                    "is_main": main_character_id == eve_char.character_id,
                    "is_main_member": main_app_status
                    == Applications.MembershipStates.ACCEPTED,
                }
            )

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

    applications_and_skillset_status = []
    skillset_names = set()
    for application in chars_applied:

        eve_char: EveCharacter = application.eve_character
        user = get_user_from_evecharacter(eve_char)
        all_characters = get_all_characters_from_user(user)

        characters_skillset_status = {}

        for char in all_characters:
            ma_character: Character = char.memberaudit_character
            ma_character.update_skill_sets()
            for acl in existing_acls:
                characters_skillset_status.setdefault(char.character_name, {})
                for skillset in acl.skill_sets.all():
                    characters_skillset_status[char.character_name][skillset.name] = (
                        ma_character.skill_set_checks.filter(skill_set=skillset)
                        .first()
                        .can_fly
                    )
                    skillset_names.add(skillset.name)

        applications_and_skillset_status.append(
            {"application": application, "skill_sets": characters_skillset_status}
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

    # @@@ TODO: Add a view for auditing history of all application changes (paginated)

    context = {
        "accepted_chars": chars_accepted,
        "rejected_chars": chars_rejected,
        "applied_chars": applications_and_skillset_status,
        "existing_acls": existing_acls,
        "skillset_names": list(skillset_names),
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

    eve_char_application = owned_chars_query[0].applications

    # Check if not already a member
    if eve_char_application.member_state == Applications.MembershipStates.ACCEPTED:
        return redirect("/whctools")

    # Check if rejected
    if eve_char_application.member_state == Applications.MembershipStates.REJECTED:
        return redirect("/whctools")

    eve_char_application.member_state = Applications.MembershipStates.APPLIED
    eve_char_application.save()

    log_application_change(eve_char_application)

    notify.info(
        request.user,
        "WHC application: Application Submitted",  # @@@ todo, individual application to different communities
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

    return redirect("/whctools/staff")


# @@@ TODO - Add to the views.html templates the ability to remove from specific acls
@login_required
@permission_required("whctools.whc_officer")
def reject(request, char_id, reason, days, acl_name="WHC"):

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

        elif reason == "skills":
            # WHC CL Morra states that only one character on an account has to meet the skill requirements - therefor, if none meet them reject all
            rejection_reason = Applications.RejectionStates.SKILLS
            notification_names = remove_all_alts(
                acl_name,
                member_application,
                Applications.MembershipStates.REJECTED,
                rejection_reason,
                days,
            )

        else:
            # Other can be used for individual removal of alts that need cleaning up.
            # note: currently only used on the reject an openapplication - additional @@@ TODO to hook up to the remove membership page
            logger.debug(
                f"Singleton removal of {member_application.eve_character.character_name}"
            )
            rejection_reason = Applications.RejectionStates.OTHER
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

    return redirect("/whctools/staff")


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

        mains_and_alts[user_obj.id].setdefault("alts", []).append(memb)
        mains_and_alts[user_obj.id].setdefault(
            "complete_alts", get_all_characters_from_user(user_obj)
        )

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
