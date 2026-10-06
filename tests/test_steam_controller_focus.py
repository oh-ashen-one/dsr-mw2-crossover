import unittest
from dsr_mw2.steam_controller_focus import set_disabled, SETTINGS

class SteamFocusTests(unittest.TestCase):
    def test_preserves_other_content_and_is_idempotent(self):
        before='"UserLocalConfigStore"\n{\n\t"other" "escaped \\" text { }"\n\t"system"\n\t{\n\t\t"EnableGameOverlay" "1"\n\t}\n}\n'
        # Literal quoted-string escapes, braces and untouched data survive.
        changed,old=set_disabled(before,SETTINGS[0]);self.assertEqual(old,'1')
        self.assertEqual(changed,before.replace('"EnableGameOverlay" "1"','"EnableGameOverlay" "0"'))
        changed,old=set_disabled(changed,SETTINGS[1]);self.assertIsNone(old)
        again,old=set_disabled(changed,SETTINGS[1]);self.assertEqual(again,changed);self.assertEqual(old,'0')
        self.assertIn('"other" "escaped \\" text { }"',changed)

    def test_ambiguous_or_unexpected_setting_fails(self):
        for body in ['"Controller_CheckGuideButton" "9"',
                     '"Controller_CheckGuideButton" "0" "Controller_CheckGuideButton" "1"',
                     '"Controller_CheckGuideButton" { }']:
            with self.assertRaises(ValueError):set_disabled('"UserLocalConfigStore" {'+body+'}',SETTINGS[1])

    def test_never_edits_same_name_in_other_block(self):
        before='"other" {"Controller_CheckGuideButton" "1"} "UserLocalConfigStore" {}'
        changed,_=set_disabled(before,SETTINGS[1]);self.assertTrue(changed.startswith('"other" {"Controller_CheckGuideButton" "1"}'))
