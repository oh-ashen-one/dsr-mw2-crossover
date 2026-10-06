import unittest
from dsr_mw2.steam_controller_ownership import exclude_dualsense

class ControllerOwnershipTests(unittest.TestCase):
    def config(self,body):
        return '"InstallConfigStore" {'+body+' "Software" {"Valve" {"Steam" {}}} "other" {"controller_blacklist" "1234/5678"}}'

    def test_insert_only_private_steam_block_and_idempotent(self):
        before=self.config('"unrelated" "keep"');after,old=exclude_dualsense(before)
        self.assertIsNone(old);self.assertIn('"unrelated" "keep"',after)
        self.assertIn('"other" {"controller_blacklist" "1234/5678"}',after)
        self.assertEqual(exclude_dualsense(after),(after,'54c/ce6'))

    def test_preserve_existing_devices_and_recognize_padded_id(self):
        text=self.config('"controller_blacklist" "45e/2e0"')
        self.assertEqual(exclude_dualsense(text)[0],text.replace('45e/2e0','45e/2e0,54c/ce6'))
        text=self.config('"controller_blacklist" "054C/0CE6"')
        self.assertEqual(exclude_dualsense(text)[0],text)

    def test_reject_ambiguous_or_non_device_values(self):
        for body in ['"controller_blacklist" "*"','"controller_blacklist" {}','"controller_blacklist" "" "controller_blacklist" ""']:
            with self.assertRaises(ValueError):exclude_dualsense(self.config(body))
