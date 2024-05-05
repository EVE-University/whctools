"""Models."""

from django.db import models

from allianceauth.eveonline.models import EveCharacter


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
