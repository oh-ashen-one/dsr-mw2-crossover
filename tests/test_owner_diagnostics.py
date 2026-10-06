import io
import json
import hashlib
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from dsr_mw2 import owner_diagnostics as diagnostics, launch


class OwnerDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bottle = self.root / 'bottle'
        self.bottle.mkdir()
        self.payload = b'MZ-original-test-fixture-not-an-executable'
        self.record = {'file': diagnostics.PROBE, 'schema': 3,
                       'sha256': hashlib.sha256(self.payload).hexdigest(), 'bytes': len(self.payload),
                       'capture_seconds': 120, 'max_wait_for_character_seconds': 300,
                       'process_access': ['PROCESS_VM_READ', 'PROCESS_QUERY_INFORMATION', 'SYNCHRONIZE']}
        self.sources = {}
        for name in ('native/src/read_only_probe.cpp', 'native/src/dsr_snapshot.cpp', 'native/include/dsr_snapshot.hpp'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('// original fixture\n')
            self.sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        (self.root / 'evidence').mkdir()
        self.receipt = self.root / 'evidence/owner-probe-build.json'
        self.receipt.write_text(json.dumps({'external_probe': self.record, 'source_sha256': self.sources}))
        source = self.root / 'tooling-local/native-observer' / diagnostics.PROBE
        source.parent.mkdir(parents=True)
        source.write_bytes(self.payload)

    def test_stage_only_private_tool_and_never_run(self):
        with patch.object(diagnostics, 'guard', return_value=[]), \
             patch.object(diagnostics, 'bottle_processes', return_value=[]), \
             patch.object(diagnostics.subprocess, 'Popen') as execute:
            report = diagnostics.stage(self.root, self.bottle)
            self.assertTrue(report['staged'])
            self.assertFalse(report['probe_executed'])
            self.assertFalse(report['game_launched'])
            self.assertEqual(diagnostics.staged_path(self.bottle, self.record).read_bytes(), self.payload)
            execute.assert_not_called()

    def test_new_build_leaves_legacy_probe_untouched(self):
        legacy=self.bottle/'drive_c/Tools/DSR-MW2/observer-v3'/diagnostics.PROBE
        legacy.parent.mkdir(parents=True);legacy.write_bytes(b'preserved previous original build')
        with patch.object(diagnostics,'guard',return_value=[]), \
             patch.object(diagnostics,'bottle_processes',return_value=[]):
            diagnostics.stage(self.root,self.bottle)
        self.assertEqual(legacy.read_bytes(),b'preserved previous original build')
        self.assertEqual(diagnostics.staged_path(self.bottle,self.record).read_bytes(),self.payload)

    def test_staging_preserves_differing_file_and_active_session(self):
        target = diagnostics.staged_path(self.bottle, self.record)
        target.parent.mkdir(parents=True)
        target.write_bytes(b'existing')
        with patch.object(diagnostics, 'guard', return_value=[]), \
             patch.object(diagnostics, 'bottle_processes', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'size changed'):
                diagnostics.stage(self.root, self.bottle)
        self.assertEqual(target.read_bytes(), b'existing')
        with patch.object(diagnostics, 'guard', return_value=[]), \
             patch.object(diagnostics, 'bottle_processes', return_value=[77]):
            with self.assertRaisesRegex(ValueError, 'active'):
                diagnostics.stage(self.root, self.bottle)

    def test_changed_source_or_redirected_destination_refused(self):
        (self.root / 'native/src/read_only_probe.cpp').write_text('// changed\n')
        with self.assertRaisesRegex(ValueError, 'source no longer matches'):
            diagnostics.specification(self.root)
        (self.bottle / 'drive_c').mkdir()
        (self.bottle / 'drive_c/Tools').symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'destination escapes'):
            diagnostics.staged_path(self.bottle, self.record)

    def test_only_observed_single_m9_session_can_start_probe(self):
        with patch.object(diagnostics.subprocess, 'Popen') as execute:
            for mode, pids in [('stock', [1]), ('stock-online', [1]), ('steam-login', [1]), ('m9', []), ('m9', [1, 2])]:
                result = diagnostics.start(mode, pids, self.root, self.bottle, ['/usr/bin/sandbox-exec'], [])
                self.assertEqual(result['status'], 'read_only_diagnostics_skipped')
            execute.assert_not_called()

    def test_owner_observation_uses_hash_checked_tool_offline_and_no_input(self):
        target = diagnostics.staged_path(self.bottle, self.record)
        target.parent.mkdir(parents=True)
        target.write_bytes(self.payload)
        children = []
        with ExitStack() as stack:
            stack.enter_context(patch.object(diagnostics, 'guard', return_value=[]))
            stack.enter_context(patch.object(diagnostics, 'inspect_banks', return_value={'active': 'm9'}))
            stack.enter_context(patch.object(diagnostics, 'bottle_processes', return_value=[17]))
            stack.enter_context(patch.object(diagnostics, 'command', side_effect=lambda *args: ['wine-fixture', *args]))
            stack.enter_context(patch.object(diagnostics, 'environment', return_value={'private': 'test'}))
            execute = stack.enter_context(patch.object(diagnostics.subprocess, 'Popen'))
            execute.return_value.pid = 42
            result = diagnostics.start('m9', [17], self.root, self.bottle,
                                       ['/usr/bin/sandbox-exec', '-f', 'offline.sb'], children)
            self.assertEqual(result['status'], 'read_only_diagnostics_started')
            args, kwargs = execute.call_args
            self.assertEqual(args[0][-2:], [diagnostics.windows_probe(self.record), '120'])
            self.assertEqual(args[0][:3], ['/usr/bin/sandbox-exec', '-f', 'offline.sb'])
            self.assertEqual(kwargs['stdin'], diagnostics.subprocess.DEVNULL)
            self.assertEqual(kwargs['cwd'], target.parent)
            self.assertEqual((self.root / result['log']).stat().st_mode & 0o777, 0o600)
            self.assertEqual(children, [execute.return_value])
            target.write_bytes(b'broken')
            execute.reset_mock()
            failure = diagnostics.start('m9', [17], self.root, self.bottle, ['/usr/bin/sandbox-exec'], children)
            self.assertEqual(failure['status'], 'read_only_diagnostics_unavailable')
            execute.assert_not_called()

    def test_corrupt_receipt_does_not_interrupt_owner_play(self):
        self.receipt.write_text('[]')
        with patch.object(diagnostics, 'guard', return_value=[]), \
             patch.object(diagnostics, 'inspect_banks', return_value={'active': 'm9'}), \
             patch.object(diagnostics, 'bottle_processes', return_value=[1]), \
             patch.object(diagnostics.subprocess, 'Popen') as execute:
            result = diagnostics.start('m9', [1], self.root, self.bottle, ['/usr/bin/sandbox-exec'], [])
            self.assertEqual(result['status'], 'read_only_diagnostics_unavailable')
            execute.assert_not_called()

    def test_watcher_dispatches_diagnostics_once_and_only_after_game_appears(self):
        child = Mock()
        child.poll.return_value = None
        callback = Mock(return_value={'status': 'read_only_diagnostics_started'})
        with patch.object(launch, 'game_processes', side_effect=[[], [17], [17], []]), \
             patch.object(launch.time, 'sleep'), \
             patch('sys.stdout', new_callable=io.StringIO):
            self.assertTrue(launch.watch_game(child, on_started=callback))
        callback.assert_called_once_with([17])
