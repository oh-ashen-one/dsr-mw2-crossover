import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dsr_mw2 import window_controls as controls

CONFIG = ('[DisplaySetting]\nWindowMode=0\n[DisplaySettingWindow]\nLeft=0\nTop=0\nWidth=3440\nHeight=1440\n'
          '[DisplaySettingFullScreen]\nWidth=3440\nHeight=1440\n[KeyConfigAction]\nAction=81\n')


class WindowControlsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bottle = self.root / 'bottle'
        self.bottle.mkdir()
        self.config = self.bottle / controls.CONFIG
        self.config.parent.mkdir(parents=True)
        self.config.write_text(CONFIG)
        source = self.root / controls.SOURCE
        source.parent.mkdir(parents=True)
        source.write_bytes(b'original fixture source')
        self.out = self.root / 'tooling-local/window-controls'
        self.out.mkdir(parents=True)
        payload = b'MZ fixture: not executable'
        (self.out / controls.EXE).write_bytes(payload)
        self.record = {'source': controls.SOURCE, 'source_sha256': controls.digest(source.read_bytes()),
                       'file': controls.EXE, 'sha256': controls.digest(payload), 'bytes': len(payload)}
        (self.out / 'build.json').write_text(json.dumps(self.record))

    def test_display_only_edit_preserves_crlf_and_nonwindow_settings(self):
        before = CONFIG.replace('\n', '\r\n')
        after = controls.windowed_config(before)
        self.assertIn('Width=1600\r\nHeight=900\r\n', after)
        self.assertIn('WindowMode=0\r\n', after)
        self.assertEqual(after.split('[DisplaySettingFullScreen]')[1], before.split('[DisplaySettingFullScreen]')[1])
        self.assertEqual(controls.windowed_config(after), after)
        for broken in (CONFIG + '[DisplaySetting]\nWindowMode=1\n', CONFIG.replace('Height=1440\n', '', 1)):
            with self.assertRaises(ValueError):controls.windowed_config(broken)

    def test_closed_profile_backup_and_owner_later_resolution_preserved(self):
        with patch.object(controls, 'guard', return_value=[]), patch.object(controls, 'bottle_processes', return_value=[]), \
                patch.object(controls.subprocess, 'Popen') as execute:
            result = controls.stage(self.root, self.bottle)
            self.assertTrue(result['configuration_changed'])
            receipt = json.loads((self.bottle / controls.RECEIPT).read_text())
            self.assertEqual((self.bottle / receipt['backup']).read_text(), CONFIG)
            self.config.write_text(self.config.read_text().replace('Width=1600', 'Width=1920'))
            self.assertFalse(controls.stage(self.root, self.bottle)['configuration_changed'])
            self.assertIn('Width=1920', self.config.read_text())
            execute.assert_not_called()

    def test_borderless_receipt_migrates_once_without_resetting_owner_size(self):
        before = CONFIG.replace('WindowMode=0', 'WindowMode=1')
        self.config.write_text(before)
        (self.bottle / controls.RECEIPT).write_text('{"version":1,"enabled":true}')
        with patch.object(controls, 'guard', return_value=[]), patch.object(controls, 'bottle_processes', return_value=[]):
            self.assertTrue(controls.stage(self.root, self.bottle)['configuration_changed'])
            self.assertEqual(self.config.read_text(), before.replace('WindowMode=1', 'WindowMode=0'))
            receipt = json.loads((self.bottle / controls.RECEIPT).read_text())
            self.assertEqual(receipt['version'], 2)
            self.assertEqual((self.bottle / receipt['mode_fix_backup']).read_text(), before)
            self.assertFalse(controls.stage(self.root, self.bottle)['configuration_changed'])

    def test_active_profile_changed_build_and_redirect_are_refused(self):
        with patch.object(controls, 'guard', return_value=[]), patch.object(controls, 'bottle_processes', return_value=[7]):
            with self.assertRaisesRegex(ValueError, 'active'):controls.stage(self.root, self.bottle)
        self.assertEqual(self.config.read_text(), CONFIG)
        (self.out / controls.EXE).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):controls.specification(self.root)
        with tempfile.TemporaryDirectory() as external:
            self.config.unlink();self.config.symlink_to(Path(external) / 'outside.ini')
            with self.assertRaisesRegex(ValueError, 'redirected'):controls.safe(self.config, self.bottle)

    def test_game_launch_not_possible_and_ambiguous_sessions_skipped(self):
        with patch.object(controls.subprocess, 'Popen') as execute:
            for mode, pids in [('stock', [7]), ('steam-login', [7]), ('m9-test', []), ('m9', [7, 8])]:
                result = controls.start(mode, pids, self.root, self.bottle, [], [])
                self.assertEqual(result['status'], 'window_controls_skipped')
            execute.assert_not_called()

    def test_start_requires_owned_pid_and_offline_context(self):
        (self.bottle / controls.RECEIPT).write_text('{"enabled":true}')
        with patch.object(controls, 'guard', return_value=[]), patch.object(controls, 'bottle_processes', return_value=[7]), \
                patch.object(controls.subprocess, 'Popen') as execute:
            for pids, prefix in [([8], ['/usr/bin/sandbox-exec']), ([7], [])]:
                result = controls.start('m9-test', pids, self.root, self.bottle, prefix, [])
                self.assertEqual(result['status'], 'window_controls_unavailable')
            execute.assert_not_called()

    def test_helper_starts_only_after_owned_game_and_targets_private_executable(self):
        with patch.object(controls, 'guard', return_value=[]), patch.object(controls, 'bottle_processes', return_value=[]):
            controls.stage(self.root, self.bottle)
        game = self.bottle / 'drive_c/Games/DSR-MW2'
        game.mkdir(parents=True)
        alias = self.bottle / 'drive_c/Program Files (x86)/Steam/steamapps/common/DARK SOULS REMASTERED'
        alias.parent.mkdir(parents=True);alias.symlink_to(game, target_is_directory=True)
        children = []
        with patch.object(controls, 'guard', return_value=[]), patch.object(controls, 'bottle_processes', return_value=[7]), \
                patch.object(controls, 'environment', return_value={}), \
                patch.object(controls, 'command', side_effect=lambda *args: ['wine-fixture', *args]), \
                patch.object(controls.subprocess, 'Popen') as execute:
            execute.return_value.pid = 42
            result = controls.start('m9-test', [7], self.root, self.bottle, ['/usr/bin/sandbox-exec', '-f', 'offline.sb'], children)
            self.assertEqual(result['status'], 'window_controls_started')
            args = execute.call_args.args[0]
            self.assertEqual(args[-1], '--watch')
            self.assertTrue(args[-2].startswith('C:\\Tools\\DSR-MW2\\window-controls\\'))
            self.assertEqual(children, [execute.return_value])
