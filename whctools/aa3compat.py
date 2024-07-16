from django.contrib.auth.models import User

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from whctools import __title__

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


def get_all_related_characters_from_character(character: EveCharacter):
    """helper function for getting all the characters/alts of a particular character"""
    user_obj = bc_get_user_from_eve_character(character)
    return bc_get_all_characters_from_user(user_obj)


def bc_get_main_character_name_from_user(user: User):
    """
    3.0 Backwards compatible version of framework.api.user.get_main_character_name_from_user
    """
    if user is None:
        return None

    try:
        main_character = user.profile.main_character.character_name
    except AttributeError:
        return None

    return main_character


def bc_get_all_characters_from_user(user: User):
    """
    3.0 Backwards compatible version of framework.api.user.get_all_characters_from_user
    """
    if user is None:
        return []

    try:
        characters = [
            char.character for char in CharacterOwnership.objects.filter(user=user)
        ]
    except AttributeError:
        return []

    return characters


def bc_get_user_from_eve_character(character: EveCharacter):
    """
    3.0 Backwards compatible version of framework.api.evecharacter import get_user_from_evecharacter
    """
    try:
        userprofile = character.character_ownership.user.profile
    except (
        AttributeError,
        EveCharacter.character_ownership.RelatedObjectDoesNotExist,
        CharacterOwnership.user.RelatedObjectDoesNotExist,
    ):
        # replaces get_sentinel_user wrapper from 4.0
        # basically getting a user object of some kind to return, even if its an 'empty' one
        return User.objects.get_or_create(username="deleted")[0]

    return userprofile.user


def bc_get_main_character_from_evecharacter(character: EveCharacter):
    """
    3.0 Backwards compatible version of framework.api.evecharacter import get_main_character_from_evecharacter
    """
    try:
        userprofile = character.character_ownership.user.profile

    except (
        AttributeError,
        EveCharacter.character_ownership.RelatedObjectDoesNotExist,
        CharacterOwnership.user.RelatedObjectDoesNotExist,
    ):
        return None

    return userprofile.main_character
