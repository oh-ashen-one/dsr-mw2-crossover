import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dsr_mw2.controller_setup import set_hidraw_disabled, configure


class ControllerSettingTests(unittest.TestCase):
    def registry(self, value=''):
        return ('WINE REGISTRY Version 2\n\n[Unrelated] 9\n"Keep"="yes"\n\n'
                '[System\\\\CurrentControlSet\\\\Services\\\\winebus] 1\n'
                '#time=1\n' + value + '"Start"=dword:00000003\n\n'
                '[Next] 2\n"DisableHidraw"=dword:00000000\n')

    def test_only_adds_one_line_in_winebus(self):
        source = self.registry()
        updated, prior = set_hidraw_disabled(source)
        self.assertIsNone(prior)
        self.assertEqual(updated.replace('"DisableHidraw"=dword:00000001\n', '', 1), source)

    def test_replaces_false_and_is_idempotent(self):
        source = self.registry('"DisableHidraw"=dword:00000000\n')
        updated, prior = set_hidraw_disabled(source)
        self.assertEqual(prior, '"DisableHidraw"=dword:00000000')
        self.assertEqual(updated, source.replace(prior, '"DisableHidraw"=dword:00000001', 1))
        self.assertEqual(set_hidraw_disabled(updated)[0], updated)

    def test_ambiguous_or_unexpected_settings_preserved(self):
        for source in ('', self.registry() + self.registry(),
                       self.registry('"DisableHidraw"="bad"\n'),
                       self.registry('"DisableHidraw"=dword:00000000\n' * 2)):
            with self.assertRaises(ValueError):
                set_hidraw_disabled(source)

    def test_configuration_receipt_and_repeated_call_preserve_other_values(self):
        with TemporaryDirectory() as tmp, patch('dsr_mw2.controller_setup.guard', return_value=[]), \
             patch('dsr_mw2.controller_setup.bottle_processes', return_value=[]):
            bottle = Path(tmp)
            registry = bottle / 'system.reg'
            original = self.registry().encode()
            registry.write_bytes(original)
            report = configure(bottle)
            self.assertIsNone(report['previous_line'])
            self.assertEqual(registry.read_text().replace('"DisableHidraw"=dword:00000001\n', '', 1), original.decode())
            receipt = (bottle / '.dsr-mw2-controller.json').read_bytes()
            self.assertFalse(configure(bottle)['changed'])
            self.assertEqual((bottle / '.dsr-mw2-controller.json').read_bytes(), receipt)

    def test_active_private_session_refuses_setting_changes(self):
        with TemporaryDirectory() as tmp, patch('dsr_mw2.controller_setup.guard', return_value=[]), \
             patch('dsr_mw2.controller_setup.bottle_processes', return_value=[999]):
            bottle = Path(tmp)
            registry = bottle / 'system.reg'
            registry.write_text(self.registry())
            with self.assertRaisesRegex(ValueError, 'active'):
                configure(bottle)
            self.assertEqual(registry.read_text(), self.registry())
            self.assertFalse((bottle / '.dsr-mw2-controller.json').exists())


if __name__ == '__main__':
    unittest.main()
