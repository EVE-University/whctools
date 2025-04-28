"""Models."""

from memberaudit.models import SkillSet

from django import forms
from django.contrib.auth.models import Group
from django.db import models

from allianceauth.eveonline.models import EveCharacter

try:
    # Alliance auth 4.0 only
    from allianceauth.framework.api.evecharacter import (
        get_main_character_from_evecharacter,
    )
except Exception:
    # Alliance 3.0 backwards compatibility
    from .aa3compat import (
        bc_get_main_character_from_evecharacter as get_main_character_from_evecharacter,
    )


class General(models.Model):
    """A meta model for app permissions."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("basic_access", "Can access this app"),
            ("whc_officer", "Can access officer side"),
        )


class Applications(models.Model):
    """Applications model for WHC

    Args:
        models (_type_): _description_
    """

    class MembershipStates(models.IntegerChoices):
        NOTAMEMBER = 0, "Not A Member"
        APPLIED = 1, "Applied"
        REJECTED = 2, "Rejected"
        ACCEPTED = 3, "Accepted"

    class RejectionStates(models.IntegerChoices):
        NONE = 0, "Not Rejected"
        SKILLS = 1, "Insufficient Skills"
        WITHDRAWN = 2, "Withdrawn Application"
        REMOVED = 3, "Removed From Community"
        LEFT_ALLIANCE = 4, "Left Alliance"
        LEFT_COMMUNITY = 5, "Voluntarily Left"
        OTHER = 99, "Undisclosed"

    eve_character = models.OneToOneField(
        EveCharacter, on_delete=models.CASCADE, primary_key=True
    )

    member_state = models.IntegerField(
        choices=MembershipStates.choices, default=MembershipStates.NOTAMEMBER
    )
    reject_reason = models.IntegerField(
        choices=RejectionStates.choices, default=RejectionStates.NONE
    )
    reject_timeout = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.eve_character.character_name

    class Meta:
        ordering = ["eve_character__character_name"]
        verbose_name_plural = "Applications"

    def get_main_character(self):
        return get_main_character_from_evecharacter(self.eve_character)


class ApplicationHistory(models.Model):

    date_of_change = models.DateTimeField(auto_now_add=True)
    old_state = models.IntegerField(
        choices=Applications.MembershipStates.choices,
        default=Applications.MembershipStates.NOTAMEMBER,
    )
    new_state = models.IntegerField(
        choices=Applications.MembershipStates.choices,
        default=Applications.MembershipStates.NOTAMEMBER,
    )
    reject_reason = models.IntegerField(
        choices=Applications.RejectionStates.choices,
        default=Applications.RejectionStates.NONE,
    )
    application = models.ForeignKey(
        Applications, null=True, on_delete=models.SET_NULL, related_name="app_history"
    )

    class Meta:
        ordering = ["date_of_change"]
        verbose_name_plural = "Application Log"

    def __str__(self) -> str:
        if self.application is None:
            return "(Invalid application action)"
        return f"{self.application.eve_character.character_name} - {self.get_old_state_display()} to {self.get_new_state_display()}"


class Acl(models.Model):
    """
    model of ACLs that are 'managed' by this plugin (managed being a very loose term)
    """

    name = models.CharField(max_length=255, null=False, blank=True, primary_key=True)
    description = models.TextField(null=True, blank=True)
    characters = models.ManyToManyField(EveCharacter, blank=True)
    skill_sets = models.ManyToManyField(SkillSet)
    # Each ACL can be associated with zero or more groups. When a WHC application is
    # accepted to the ACL, the user is also added to all groups. When the user's
    # last character is removed from the ACL, the user is removed from all groups.
    #
    # N.B.- Probably not a good idea to share these groups outside of whctools. It
    # will fight for control and you'll probably end up with corrupted state.
    groups = models.ManyToManyField(Group, blank=True)

    def __str__(self):
        return self.name


class ACLHistory(models.Model):

    class ApplicationStateChangeReason(models.IntegerChoices):
        NONE = 0, "No Change / Initial Acceptance"
        ACCEPTED = 1, "Application Accepted"
        LEFT_UNI = 2, "Character left Uni or Uni Affiliated"
        REMOVED = 3, "Character was removed from ACL by an Officer"
        LEFT_GROUP = 4, "Left on their own choice"
        OTHER = 99, "Other: See details"

    date_of_change = models.DateTimeField()
    old_state = models.IntegerField(
        choices=Applications.MembershipStates.choices,
        default=Applications.MembershipStates.NOTAMEMBER,
    )
    new_state = models.IntegerField(
        choices=Applications.MembershipStates.choices,
        default=Applications.MembershipStates.NOTAMEMBER,
    )
    reason_for_change = models.IntegerField(
        choices=ApplicationStateChangeReason.choices,
        default=ApplicationStateChangeReason.NONE,
    )
    changed_by = models.CharField(max_length=225, null=False, blank=True)
    acl = models.ForeignKey(Acl, on_delete=models.CASCADE, related_name="changes")
    character = models.ForeignKey(EveCharacter, null=True, on_delete=models.SET_NULL)


class DateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"


class AclHistoryRequest(forms.ModelForm):
    limit = forms.IntegerField(widget=forms.NumberInput())
    character_name = forms.CharField(required=False, widget=forms.TextInput())

    class Meta:
        model = ACLHistory
        fields = ["date_of_change"]
        widgets = {"date_of_change": DateTimeInput()}


class WelcomeMail(models.Model):
    mail_content = models.TextField(null=True, blank=True)
