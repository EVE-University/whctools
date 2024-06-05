from django.test import TestCase
from unittest.mock import patch, MagicMock
from whctools.models import EveCharacter, Acl, Applications
from whctools.signals import leaves_uni
from whctools.app_settings import IVY_LEAGUE_ALLIANCE, IVY_LEAGUE_ALT_ALLIANCE

class LeavesUniSignalTest(TestCase):
    def setUp(self):
        # Create a mock EveCharacter instance
        self.character = EveCharacter.objects.create(
            pk=1,
            character_id=123456,
            character_name="Test Character",
            alliance_id=12345  # Set an alliance ID that is not in IVY_LEAGUE_ALLIANCE or IVY_LEAGUE_ALT_ALLIANCE
        )

    @patch('whctools.signals.get_user_from_evecharacter')
    @patch('whctools.signals.remove_in_process_application')
    @patch('whctools.signals.remove_character_from_acls')
    def test_leaves_uni(self, mock_remove_character_from_acls, mock_remove_in_process_application, mock_get_user_from_evecharacter):
        # Mock the user return value
        mock_user = MagicMock()
        mock_get_user_from_evecharacter.return_value = mock_user

        # Mock the Applications.MembershipStates constants
        Applications.MembershipStates.APPLIED = 'applied'
        Applications.MembershipStates.ACCEPTED = 'accepted'

        # Create related Acl and Application instances
        acl = Acl.objects.create(name="Test ACL")
        acl.characters.add(self.character)

        application = Applications.objects.create(
            character=self.character,
            member_state=Applications.MembershipStates.ACCEPTED
        )

        # Save the character to trigger the post_save signal
        self.character.save()

        # Verify the signal logic
        mock_get_user_from_evecharacter.assert_called_once_with(character=self.character)
        mock_remove_character_from_acls.assert_called_once()

    @patch('whctools.signals.get_user_from_evecharacter')
    @patch('whctools.signals.remove_in_process_application')
    @patch('whctools.signals.remove_character_from_acls')
    def test_leaves_uni_no_acl(self, mock_remove_character_from_acls, mock_remove_in_process_application, mock_get_user_from_evecharacter):
        # Set the alliance_id to a non-ivy league alliance
        self.character.alliance_id = 54321
        self.character.save()

        # Ensure the mocks are not called since the character is not on any ACLs
        mock_get_user_from_evecharacter.assert_not_called()
        mock_remove_in_process_application.assert_not_called()
        mock_remove_character_from_acls.assert_not_called()
